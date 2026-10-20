"""品質ゲート：調査の成果物を中身で検証し、調査状態を判定する

文章や見出しが存在するかではなく、根拠となるデータ・成果物が存在し、条件を満たすかを確認する
判定基準は methodology/evaluation.md の「品質ゲート」と一致させる

状態（methodology/README.md）
- failed：自動工程が失敗した
- blocked：外部要因で必須工程を実施できない（annotations/blocked.json に理由）
- collecting：公開データの取得が終わっていない
- quantitative_complete：定量分析まで完了し、AIエージェントの工程が未着手
- qualitative_in_progress：テーマ検証・内容分析・比較のいずれかが進行中
- validation_in_progress：内容分析と比較が完了し、仮説検証・報告書・品質確認が未完了
- incomplete：報告書は書かれているが品質ゲートを通過していない
- complete：全チェックを通過した

使い方:
    python -m ycanalysis.analyze.quality_gate <slug>
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .. import METHODOLOGY_VERSION
from ..config import ROOT, load_channel, record_run

# テンプレートの記入漏れの印（「（要約）」のような通常の語は対象外）
PLACEHOLDERS = re.compile(r"要記入|TODO|未記入|（要確認[^）]*）|\{[a-z_]+\}")
HYPOTHESIS_FIELDS = ("支持", "反証", "代替説明", "確信度", "再現可能性")
EXTERNAL_TOLERANCE = 0.05     # 外部情報源との許容差（表示の丸めと更新時刻の差）
EXTERNAL_SEVERE = 0.20        # これを超える乖離は重大な異常
COUNT_TOLERANCE = 0.05        # 概要ページの動画数と取得本数の差


def _read(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def report_text(ch) -> tuple[str, str]:
    """検証対象の報告書（DRAFT_REPORT.md があればそれ、なければ FINAL_REPORT.md）"""
    for name in ("DRAFT_REPORT.md", "FINAL_REPORT.md"):
        p = ch.report_dir / name
        if p.exists():
            return name, p.read_text()
    return "", ""


def sections(text: str) -> dict[str, str]:
    """「## N. 見出し」ごとの本文"""
    parts = re.split(r"^## (\d+)\.", text, flags=re.M)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def hypothesis_blocks(text: str) -> list[str]:
    """仮説ブロック（### または ## で始まる H1・H2… の節、または表の行）"""
    blocks = re.split(r"^#{2,4} *H\d+", text, flags=re.M)[1:]
    rows = [ln for ln in text.splitlines() if re.match(r"^\| *H\d+", ln)]
    return blocks + rows


def hypothesis_complete(block: str) -> bool:
    return all(f in block for f in HYPOTHESIS_FIELDS) or block.startswith("|") and block.count("|") >= 7


def check(ok: bool, evidence: str) -> dict:
    return {"ok": bool(ok), "evidence": evidence}


def data_checks(ch) -> dict:
    c = {}
    audit_p = ch.processed_dir / "subscriber_audit.csv"
    audit = pd.read_csv(audit_p) if audit_p.exists() else pd.DataFrame()
    direct = audit[(audit.get("source") == "direct")] if len(audit) else audit
    cur = direct[direct["status"] == "有効"].tail(1) if len(direct) else direct
    cur_val = float(cur["subscribers"].iloc[0]) if len(cur) else None
    c["channel_identity"] = check(
        len(cur) > 0, f"概要ページ {cur['file'].iloc[0]} の {cur['subscriber_source'].iloc[0]} から対象IDの値を取得"
        if len(cur) else "概要ページから対象チャンネルの登録者数を取得できていない")
    c["current_subscriber_source"] = check(
        len(cur) > 0 and cur["subscriber_source"].iloc[0] in ("channel_id_node", "page_owner_header", "handle_header",
                                                            "channel_id_html"),
        f"{cur['subscriber_text'].iloc[0]}（{cur['subscriber_precision'].iloc[0]}）" if len(cur) else "なし")

    # 外部情報源：as_of（その値の時点）があれば、14日以内で最も近い観測値と比べる。なければ現在値と比べる
    ext = json.loads(_read(ch.annotations_dir / "external_checks.json") or "[]")
    confirmed = [e for e in ext if e.get("channel_id_confirmed") and e.get("subscribers")]
    obs = audit[audit["status"] == "有効"].copy() if len(audit) else audit
    if len(obs):
        obs["t"] = pd.to_datetime(obs["snapshot_at"], utc=True, format="mixed")
    rows = []
    for e in confirmed:
        ref, ref_at = cur_val, "現在値"
        if e.get("as_of") and len(obs):
            t = pd.Timestamp(e["as_of"], tz="UTC")
            gap = (obs["t"] - t).abs()
            if gap.min() <= pd.Timedelta(days=14):
                r = obs.loc[gap.idxmin()]
                ref, ref_at = float(r["subscribers"]), f"{r['t']:%Y-%m-%d} の観測"
            else:
                ref = None
        if ref:
            rows.append((e, abs(e["subscribers"] - ref) / ref, ref_at))
    if rows:
        worst = max(d for _, d, _ in rows)
        c["cross_source"] = check(
            min(d for _, d, _ in rows) <= EXTERNAL_TOLERANCE and worst <= EXTERNAL_SEVERE,
            "、".join(f"{e['source']} {e['subscribers']:,}（{e.get('as_of', e.get('retrieved_at', ''))}、{ref_at}との差{d:.1%}）"
                     for e, d, ref_at in rows) + ("" if worst <= EXTERNAL_SEVERE else "  重大な乖離あり"))
    else:
        c["cross_source"] = check(False, "annotations/external_checks.json に同一性を確認した外部情報源がない")

    if len(audit):
        used = audit[audit["status"].isin(["有効", "疑義あり"])]
        invalid = audit[audit["status"] == "無効"]
        c["history_validated"] = check(
            len(used) > 0 and used["identity_validated"].astype(bool).all(),
            f"観測 {len(audit)} 件：有効 {int((audit['status'] == '有効').sum())}、疑義あり "
            f"{int((audit['status'] == '疑義あり').sum())}、無効 {len(invalid)}、重複 {int((audit['status'] == '重複').sum())}")
        c["anomalies_explained"] = check(
            audit.loc[audit["status"] != "有効", "note"].fillna("").str.len().gt(0).all()
            if (audit["status"] != "有効").any() else True,
            "有効以外の全観測に理由が記録されている")
    else:
        c["history_validated"] = check(False, "processed/subscriber_audit.csv がない")
        c["anomalies_explained"] = check(False, "processed/subscriber_audit.csv がない")

    info = json.loads(_read(ch.processed_dir / "build_info.json") or "{}")
    limited = (info.get("videos_source") or {}).get("limit_per_tab")
    page_count = cur["video_count"].iloc[0] if len(cur) else None
    n = sum((info.get("kinds") or {}).values())
    if limited:
        c["counts_consistent"] = check(False, f"各タブ {limited} 本に限定した取得のため全体の整合性を確認できない")
    elif page_count and page_count == page_count:
        d = abs(n - page_count) / page_count
        c["counts_consistent"] = check(d <= COUNT_TOLERANCE, f"概要ページ {int(page_count)} 本、取得 {n} 本（差 {d:.1%}）")
    else:
        c["counts_consistent"] = check(False, "概要ページの動画数がない")

    mc = ch.processed_dir / "milestone_candidates.csv"
    if mc.exists():
        m = pd.read_csv(mc)
        bad = m[m["accepted"] & m["title"].str.contains("人口|商圏|来場|利用者|乗降|都市")]
        c["milestones_valid"] = check(bad.empty, f"候補 {len(m)} 件、採用 {int(m['accepted'].sum())} 件、"
                                                 f"人数表現の誤採用 {len(bad)} 件")
    else:
        c["milestones_valid"] = check(False, "processed/milestone_candidates.csv がない（quant 未実行）")

    name, text = report_text(ch)
    if cur_val and text:
        forms = {f"{int(cur_val):,}", f"{cur_val / 10000:g}万", f"{cur_val / 10000:.1f}万"}
        c["report_uses_validated_subscribers"] = check(any(f in text for f in forms),
                                                       f"{name} に検証済みの現在値（{'・'.join(sorted(forms))}）がある")
    else:
        c["report_uses_validated_subscribers"] = check(False, "報告書または検証済みの現在値がない")
    return c


def analysis_checks(ch) -> dict:
    c = {}
    brief = _read(ROOT / "docs" / f"{ch.slug}-analysis.md")
    purpose = re.search(r"^## (?:\d+\.\s*)?(?:調査)?目的\s*\n(.*?)(?=\n## |\Z)", brief, re.S | re.M)
    ptxt = purpose.group(1).strip() if purpose else ""
    c["research_question"] = check(len(ptxt) >= 40 and "（このチャンネルについて" not in ptxt,
                                   f"docs/{ch.slug}-analysis.md の調査目的 {len(ptxt)} 字")

    c["quantitative_analysis"] = check((ch.report_dir / "phase2_tables.md").exists()
                                       and (ch.processed_dir / "analysis_videos.csv").exists(),
                                       "phase2_tables.md と analysis_videos.csv")

    tv = json.loads(_read(ch.annotations_dir / "theme_validation.json") or "{}")
    manual = (ch.annotations_dir / "labels_manual.csv").exists()
    kappa, agree, n_checked = tv.get("kappa"), tv.get("agreement"), tv.get("n_checked", 0)
    theme_ok = (manual and tv.get("validated", True) is not False) or (
        bool(tv.get("validated")) and n_checked >= 50 and ((kappa or 0) >= 0.6 or (agree or 0) >= 0.8))
    c["theme_classification_validated"] = check(
        theme_ok, f"手作業ラベル {'あり' if manual else 'なし'}、検証 {n_checked} 本、κ={kappa}、一致率={agree}")

    coding_p = ch.annotations_dir / "phase3_coding.csv"
    coding = pd.read_csv(coding_p) if coding_p.exists() else pd.DataFrame()
    if len(coding) and "tier" in coding:
        tiers = coding["tier"].value_counts().to_dict()
        c["tier_comparison"] = check(tiers.get("high", 0) >= 5 and tiers.get("low", 0) >= 5,
                                     f"コーディング {len(coding)} 本 {tiers}")
        ids = coding["video_id"].tolist()
        subs = sum(any((ch.raw_dir / "subs").glob(f"{v}.*json3")) for v in ids)
        frames = sum((ch.raw_dir / "frames" / v).exists() or (ch.raw_dir / "scene_cuts" / f"{v}.json").exists()
                     for v in ids)
        c["subtitles_and_video_checked"] = check(subs / len(ids) >= 0.9 and frames / len(ids) >= 0.9,
                                                 f"字幕 {subs}/{len(ids)} 本、映像フレーム {frames}/{len(ids)} 本")
    else:
        c["tier_comparison"] = check(False, "annotations/phase3_coding.csv がない")
        c["subtitles_and_video_checked"] = check(False, "annotations/phase3_coding.csv がない")

    _, text = report_text(ch)
    sec = sections(text)
    p4 = _read(ch.report_dir / "phase4_tables.md")
    header = re.search(r"^\| 指標 \|(.*)$", p4, re.M)
    n_peers = len([x for x in header.group(1).split("|") if x.strip()]) - 1 if header else 0
    s6 = sec.get("6", "")
    c["peer_comparison"] = check(n_peers >= 2 and "選定" in s6 and len(s6) >= 400,
                                 f"比較チャンネル {max(n_peers, 0)} 件、報告書6章 {len(s6)} 字")

    hyp_text = _read(ch.report_dir / "hypotheses.md") + "\n" + sec.get("7", "")
    blocks = hypothesis_blocks(hyp_text)
    full = [b for b in blocks if hypothesis_complete(b)]
    stages = [s for s in ("発見", "クリック", "継続", "再訪") if s in sec.get("7", "")]
    c["hypotheses_validated"] = check(len(full) >= 3 and len(stages) == 4,
                                      f"5要素がそろった仮説 {len(full)} 件、4段階の言及 {stages}")
    return c


def report_checks(ch) -> dict:
    c = {}
    name, text = report_text(ch)
    sec = sections(text)
    c["report_structure"] = check(all(str(i) in sec for i in range(1, 10)), f"{name or '報告書なし'} の章 {sorted(sec)}")
    ph = PLACEHOLDERS.findall(text)
    c["no_placeholders"] = check(bool(text) and not ph, f"未記入の印 {len(ph)} 件 {ph[:3]}")
    urls = len(set(re.findall(r"https://www\.youtube\.com/watch\?v=[\w-]{11}", text)))
    labels = all(x in text for x in ("【事実】", "【推論】"))
    s1 = sec.get("1", "")
    c["conclusions_supported"] = check(urls >= 10 and labels and "確信度" in s1,
                                       f"動画URL {urls} 本、事実・推論の区別 {'あり' if labels else 'なし'}、"
                                       f"1章の確信度 {'あり' if '確信度' in s1 else 'なし'}")
    # 引用した動画IDが、対象・比較チャンネルの取得データに実在するか（推測で書いたIDを防ぐ）
    known = set()
    for f in ("analysis_videos.csv", "peer_videos.csv", "videos.csv"):
        p = ch.processed_dir / f
        if p.exists():
            known |= set(pd.read_csv(p, usecols=["video_id"])["video_id"])
    cited = set(re.findall(r"watch\?v=([\w-]{11})", text + _read(ch.report_dir / "hypotheses.md")))
    unknown = sorted(cited - known)
    c["cited_videos_exist"] = check(bool(cited) and not unknown,
                                    f"引用 {len(cited)} 本、取得データにないID {len(unknown)} 本 {unknown[:5]}")
    bullets = lambda s: len(re.findall(r"^\s*[-|]", s, re.M))  # noqa: E731
    c["limitations"] = check(bullets(sec.get("9", "")) >= 3, f"9章の項目 {bullets(sec.get('9', ''))}")
    c["transferable_insights"] = check(bullets(sec.get("8", "")) >= 3, f"8章の項目 {bullets(sec.get('8', ''))}")
    return c


def derive_state(ch, checks: dict) -> str:
    runs = json.loads(_read(ch.report_dir / "run_info.json") or "{}")
    if any(v.get("status") == "failed" for k, v in runs.items() if k.startswith("run:")):
        return "failed"
    blocked = json.loads(_read(ch.annotations_dir / "blocked.json") or "{}")
    if blocked:
        return "blocked"
    if not (ch.processed_dir / "videos.csv").exists():
        return "collecting"
    ok = {k: v["ok"] for k, v in checks.items()}
    if all(ok.values()):
        return "complete"
    agent = ["theme_classification_validated", "tier_comparison", "subtitles_and_video_checked", "peer_comparison"]
    started = any((ch.annotations_dir / f).exists() for f in ("phase3_coding.csv", "theme_validation.json")) or \
        (ch.report_dir / "phase4_tables.md").exists()
    if not started:
        return "quantitative_complete"
    if not all(ok[k] for k in agent):
        return "qualitative_in_progress"
    name, text = report_text(ch)
    if name and ok["report_structure"] and ok["no_placeholders"]:
        return "incomplete"
    return "validation_in_progress"


NEXT_ACTIONS = {
    "cross_source": "外部統計（ユーチュラ等）の登録者数と取得日時を annotations/external_checks.json に記録する",
    "research_question": "docs/<slug>-analysis.md の調査目的を、検証済みデータの初期分析に基づいて書く",
    "theme_classification_validated": "テーマ分類を盲検で検証し annotations/theme_validation.json に κ と件数を記録する",
    "tier_comparison": "processed/phase3_sample.csv の動画を annotations/phase3_coding.csv にコーディングする",
    "subtitles_and_video_checked": "collect.ytdlp_meta subs と collect.media_sample で字幕・フレームを取得し目視する",
    "peer_comparison": "collect.search_peers → 比較チャンネルの収集 → analyze.peers、報告書6章に選定理由を書く",
    "hypotheses_validated": "reports/<slug>/hypotheses.md に5要素（支持・反証・代替説明・確信度・再現可能性）で仮説を書き、7章で4段階を論じる",
    "report_structure": "DRAFT_REPORT.md を9章構成で書く（templates/report.md）",
    "no_placeholders": "DRAFT_REPORT.md の未記入箇所を埋める",
    "conclusions_supported": "結論に動画URL・数値・【事実】【推論】の区別・確信度を付ける",
    "report_uses_validated_subscribers": "報告書の登録者数を subscriber_audit.csv の検証済みの現在値にそろえる",
    "counts_consistent": "全動画を取得する（--limit なし）か、差の理由を調べる",
    "limitations": "報告書9章に分析の限界を3項目以上書く",
    "transferable_insights": "報告書8章に他チャンネルへの応用を3項目以上書く",
    "cited_videos_exist": "報告書・仮説で引用した動画IDを processed/analysis_videos.csv から引き直す",
    "channel_identity": "collect.channel_page で概要ページを再取得し、対象IDの値が取れるか確認する",
    "history_validated": "processed/subscriber_audit.csv を確認し、無効・疑義ありの原因を調べる",
}


def evaluate(slug: str) -> dict:
    ch = load_channel(slug)
    checks = {**data_checks(ch), **analysis_checks(ch), **report_checks(ch)}
    state = derive_state(ch, checks)
    missing = [k for k, v in checks.items() if not v["ok"]]
    path = ch.report_dir / "research_status.json"
    prev = json.loads(_read(path) or "{}")
    result = {
        "slug": slug,
        "state": state,
        "methodology_version": METHODOLOGY_VERSION,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "checks": checks,
        "missing": missing,
        "next_actions": [NEXT_ACTIONS.get(k, k).replace("<slug>", slug) for k in missing],
        "steps": prev.get("steps", {}),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    record_run(ch, "quality_gate", state=state, missing=missing)
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    r = evaluate(ap.parse_args().slug)
    print(f"調査状態: {r['state']}")
    for k, v in r["checks"].items():
        print(f"  [{'OK' if v['ok'] else '--'}] {k}: {v['evidence']}")
    if r["next_actions"]:
        print("\n次の作業:")
        for a in r["next_actions"]:
            print(f"  - {a}")


if __name__ == "__main__":
    main()
