"""Rule-based article chunking for Chinese tax statutes/notices.

Bodies must remain original substrings (whitespace-normalized only).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CN_NUM = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def cn_to_int(s: str) -> int | None:
    s = s.strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    if s.startswith("十"):
        return 10 + CN_NUM.get(s[1:], 0)
    if "十" in s:
        left, right = s.split("十", 1)
        return CN_NUM.get(left, 0) * 10 + (CN_NUM.get(right, 0) if right else 0)
    if len(s) == 1 and s in CN_NUM:
        return CN_NUM[s]
    return None


def normalize_ws(text: str) -> str:
    text = text.replace("\u3000", " ").replace("&ensp;", " ").replace("&nbsp;", " ")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_chrome(text: str) -> str:
    """Drop obvious site chrome lines; keep statute body."""
    drop_prefixes = (
        "国家税务总局政策法规库",
        "本站热词",
        "个人中心",
        "网站标识码",
        "京ICP",
        "京公网安备",
        "电脑版",
        "移动端",
        "主办单位",
        "技术支持",
        "扫一扫",
        "语音播报",
        "用户登录",
        "网站纠错",
        "分享到",
        "订阅已推送",
        "阅读量",
        "当前位置",
        "字体：",
        "【打印",
        "【关闭",
        "打开微信",
        "财政部微信",
        "返回主站",
        "附件下载",
        "相关文章",
        "网站地图",
        "联系我们",
        "Android下载",
        "iphone下载",
        "移动客户端",
        "官方抖音号",
        "财政部视频号",
    )
    lines = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s in {">", "-->", "x", "简", "繁", "登录", "EN", "搜索", "高级搜索"}:
            continue
        if any(s.startswith(p) or p in s for p in drop_prefixes):
            # keep lines that are clearly statute after chrome keywords mixed? prefer drop
            if not re.match(r"^第[一二三四五六七八九十百零〇两\d]+条", s) and not re.match(
                r"^[一二三四五六七八九十]+、", s
            ):
                continue
        lines.append(s)
    return "\n".join(lines)


@dataclass
class ArticleChunk:
    clause_no: str
    body: str
    start: int
    end: int


ARTICLE_RE = re.compile(
    r"(?m)^(?P<full>第(?P<num>[一二三四五六七八九十百零〇两\d]+)条)\s*(?P<rest>.*)$"
)
ITEM_RE = re.compile(
    r"(?m)^(?P<full>(?P<num>[一二三四五六七八九十]+)、)\s*(?P<rest>.*)$"
)
SUBITEM_RE = re.compile(
    r"(?m)^(?P<full>（(?P<num>[一二三四五六七八九十]+)）)\s*(?P<rest>.*)$"
)


def split_by_pattern(text: str, pattern: re.Pattern[str], label_fmt: str) -> list[ArticleChunk]:
    matches = list(pattern.finditer(text))
    if not matches:
        return []
    chunks: list[ArticleChunk] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        num = m.group("num")
        n = cn_to_int(num)
        clause_no = label_fmt.format(n=n if n is not None else num, raw=num)
        chunks.append(ArticleChunk(clause_no=clause_no, body=body, start=start, end=end))
    return chunks


def _refine_large_items(
    source: str, chunks: list[ArticleChunk], *, max_chars: int = 2500
) -> list[ArticleChunk]:
    """Split oversized 一、/二、 bodies by （一）（二） sub-items when available."""
    out: list[ArticleChunk] = []
    for c in chunks:
        if len(c.body) <= max_chars:
            out.append(c)
            continue
        # Locate this body in source to keep absolute offsets for debugging
        abs_start = source.find(c.body)
        if abs_start < 0:
            out.append(c)
            continue
        sub_matches = list(SUBITEM_RE.finditer(c.body))
        if len(sub_matches) < 2:
            out.append(c)
            continue
        # Optional preamble before first （一）
        head = c.body[: sub_matches[0].start()].strip()
        if head and len(head) > 20:
            out.append(
                ArticleChunk(
                    clause_no=f"{c.clause_no}导语",
                    body=head,
                    start=abs_start,
                    end=abs_start + sub_matches[0].start(),
                )
            )
        for i, m in enumerate(sub_matches):
            s = m.start()
            e = sub_matches[i + 1].start() if i + 1 < len(sub_matches) else len(c.body)
            body = c.body[s:e].strip()
            raw = m.group("num")
            out.append(
                ArticleChunk(
                    clause_no=f"{c.clause_no}（{raw}）",
                    body=body,
                    start=abs_start + s,
                    end=abs_start + e,
                )
            )
    return out


def chunk_document(raw_text: str) -> tuple[str, list[ArticleChunk], str]:
    """Return (normalized_source, chunks, strategy)."""
    text = normalize_ws(strip_chrome(raw_text))
    by_article = split_by_pattern(text, ARTICLE_RE, "第{n}条")
    if len(by_article) >= 3:
        return text, by_article, "article"
    by_item = split_by_pattern(text, ITEM_RE, "第{raw}项")
    if len(by_item) >= 2:
        fixed = []
        for c in by_item:
            raw = c.clause_no.replace("第", "").replace("项", "")
            fixed.append(
                ArticleChunk(
                    clause_no=f"{raw}、",
                    body=c.body,
                    start=c.start,
                    end=c.end,
                )
            )
        refined = _refine_large_items(text, fixed)
        strategy = "item+subitem" if len(refined) > len(fixed) else "item"
        return text, refined, strategy
    # fallback: whole doc one chunk
    return text, [ArticleChunk(clause_no="全文", body=text, start=0, end=len(text))], "whole"


def fidelity_ok(source: str, body: str) -> bool:
    """Body must appear in source after light space collapse."""
    def crush(s: str) -> str:
        return re.sub(r"\s+", "", s)

    return crush(body) in crush(source) and len(body.strip()) > 0


TAG_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("税率", re.compile(r"税率|百分之|征收率")),
    ("视同销售", re.compile(r"视同应税|视同销售|无偿转让")),
    ("进项抵扣", re.compile(r"进项税额|不得.*抵扣|扣税凭证")),
    ("小规模", re.compile(r"小规模纳税人|起征点|简易计税")),
    ("留抵退税", re.compile(r"留抵|退还期末留抵")),
    ("纳税义务", re.compile(r"纳税义务发生时间|纳税地点|计税期间")),
    ("免税优惠", re.compile(r"免征增值税|税收优惠|放弃.*优惠")),
    ("发票", re.compile(r"增值税发票|电子发票|开具")),
    ("出口退税", re.compile(r"出口|零税率|免抵退")),
]


def distill_tags(body: str) -> str:
    tags = [name for name, rx in TAG_RULES if rx.search(body)]
    return ",".join(tags) if tags else "增值税"
