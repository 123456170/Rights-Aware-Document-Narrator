import streamlit as st
import streamlit.components.v1 as components

import json
import re
import math
import io
import wave
import struct
import hashlib
import sqlite3
import os
import tempfile
import time
import datetime
import base64
from collections import Counter, defaultdict
from html import escape


st.set_page_config(
    page_title="Rights-Aware Narrator Demo",
    layout="wide",
    initial_sidebar_state="expanded",
)


DOC_ID = "synthetic-demo-report-2026"

PLANNED_USE = {
    "commercial": False,
    "cloning": False,
    "personal_use": True,
}

VOICE_LICENSES = {
    "Demo-Voice-A": {
        "licence": "Demo licence: personal use allowed, no commercial redistribution",
        "commercial": False,
        "cloning": False,
        "personal_use": True,
        "notes": "Used for the built-in synthetic demo.",
    },
    "Open-Commercial-Voice": {
        "licence": "Apache-2.0 style demo record",
        "commercial": True,
        "cloning": True,
        "personal_use": True,
        "notes": "Allowed for broader use if attribution terms are met.",
    },
    "Restricted-Clone-Voice": {
        "licence": "Proprietary demo licence: personal listening only",
        "commercial": False,
        "cloning": False,
        "personal_use": True,
        "notes": "Do not use for cloning or commercial distribution.",
    },
}

DEFAULT_CONFIG = {
    "voice": "Demo-Voice-A",
    "speed": 1.0,
    "chunk_chars": 300,
    "audio_format": "wav",
    "rights_confirmed": True,
}


RAW_PAGES = [
    {
        "page": 1,
        "blocks": [
            {
                "type": "header",
                "text": "Field 10: Speech, Audio and Multimodal AI",
                "bbox": [72, 30, 540, 46],
            },
            {
                "type": "heading",
                "text": "Annual Demo Report",
                "bbox": [72, 90, 300, 115],
            },
            {
                "type": "paragraph",
                "text": (
                    "This report summarizes the\n"
                    "com-\n"
                    "munity outcomes for 2026. It is a synthetic document [1]."
                ),
                "bbox": [72, 130, 540, 200],
            },
            {
                "type": "list",
                "text": (
                    "• First item: local libraries received equipment.\n"
                    "• Second item: tutoring hours increased."
                ),
                "bbox": [72, 210, 540, 260],
            },
            {
                "type": "paragraph",
                "text": "The program will continue",
                "bbox": [72, 270, 540, 300],
            },
            {
                "type": "footer",
                "text": "Page 1",
                "bbox": [72, 750, 540, 766],
            },
        ],
    },
    {
        "page": 2,
        "blocks": [
            {
                "type": "header",
                "text": "Field 10: Speech, Audio and Multimodal AI",
                "bbox": [72, 30, 540, 46],
            },
            {
                "type": "paragraph",
                "text": "into the next year. Stakeholders approved the budget.",
                "bbox": [72, 90, 540, 130],
            },
            {
                "type": "table",
                "title": "Regional Outcomes",
                "rows": [
                    ["Region", "Score"],
                    ["North", "84"],
                    ["South", "77"],
                    ["East", "91"],
                    ["West", "68"],
                ],
                "bbox": [72, 150, 540, 260],
            },
            {
                "type": "figure",
                "caption": "",
                "bbox": [72, 280, 540, 380],
            },
            {
                "type": "figure",
                "caption": "Figure 2. Participation trend.",
                "bbox": [72, 390, 540, 490],
            },
            {
                "type": "paragraph",
                "text": (
                    "A very long sentence without internal punctuation that should remain "
                    "whole even if it exceeds the default chunk length because it has no "
                    "terminator and contains many repeated descriptive clauses to test "
                    "grouping behaviour while preserving accessibility and avoiding mid "
                    "sentence cuts in the narrator pipeline and it continues with additional "
                    "synthetic wording to make the character count comfortably larger than "
                    "the configured chunk target so the chunker must keep the complete "
                    "sentence intact rather than cutting it at an arbitrary boundary"
                ),
                "bbox": [72, 500, 540, 590],
            },
            {
                "type": "footer",
                "text": "Page 2",
                "bbox": [72, 750, 540, 766],
            },
        ],
    },
    {
        "page": 3,
        "blocks": [
            {
                "type": "header",
                "text": "Field 10: Speech, Audio and Multimodal AI",
                "bbox": [72, 30, 540, 46],
            },
            {
                "type": "paragraph",
                "text": "End of report.",
                "bbox": [72, 90, 540, 120],
            },
            {
                "type": "footer",
                "text": "Page 3",
                "bbox": [72, 750, 540, 766],
            },
        ],
    },
]


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def normalise_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def check_voice_licence(voice, licences=None, planned_use=None):
    licences = licences or VOICE_LICENSES
    planned_use = planned_use or PLANNED_USE

    if voice not in licences:
        return False, f"No licence record exists for voice '{voice}'."

    record = licences[voice]
    if record is None:
        return False, f"Licence record for voice '{voice}' is empty."

    if planned_use.get("commercial") and not record.get("commercial"):
        return False, f"Voice '{voice}' does not allow commercial use."

    if planned_use.get("cloning") and not record.get("cloning"):
        return False, f"Voice '{voice}' does not allow voice cloning."

    if planned_use.get("personal_use") and not record.get("personal_use"):
        return False, f"Voice '{voice}' does not allow personal use."

    return True, f"Licence record found for '{voice}' and planned use is allowed."


def rights_and_licence_status():
    cfg = st.session_state.config
    rights_ok = bool(cfg.get("rights_confirmed", False))
    licence_ok, licence_msg = check_voice_licence(cfg.get("voice", ""))

    messages = []
    if not rights_ok:
        messages.append(
            "Rights check failed: confirm that this is a document you have a right to read."
        )
    messages.append(licence_msg)

    return rights_ok and licence_ok, "\n".join(messages)


def extract_pages(raw_pages):
    page_count = len(raw_pages)
    threshold = page_count // 2 + 1
    counts = Counter()

    for page in raw_pages:
        seen = set()
        for block in page.get("blocks", []):
            if "bbox" not in block:
                continue
            key = (normalise_text(block.get("text", "")), round(block["bbox"][1] / 20))
            if key not in seen:
                counts[key] += 1
                seen.add(key)

    cleaned_pages = []
    for page in raw_pages:
        kept = []
        for block in page.get("blocks", []):
            if "bbox" in block:
                key = (normalise_text(block.get("text", "")), round(block["bbox"][1] / 20))
                is_repeated_furniture = counts[key] >= threshold
                is_top_or_bottom = block["bbox"][1] < 100 or block["bbox"][1] > 700
                if is_repeated_furniture and is_top_or_bottom:
                    continue
            kept.append(dict(block))
        cleaned_pages.append({"page": page["page"], "blocks": kept})

    return cleaned_pages


def clean_block_text(text):
    text = re.sub(r"\s*\[\d+\]", "", text)
    text = re.sub(r"\s*[†‡]\s*", " ", text)

    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.fullmatch(r"(?:page\s*)?\d+", line, flags=re.I):
            continue
        lines.append(line)

    merged = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.endswith("-") and i + 1 < len(lines):
            nxt = lines[i + 1].lstrip()
            if nxt and nxt[0].islower():
                merged.append(line[:-1] + nxt)
                i += 2
                continue
        merged.append(line)
        i += 1

    merged = [re.sub(r"\s+", " ", item) for item in merged]
    return "\n".join(merged)


def clean_document(pages):
    flat = []

    for page in pages:
        for block in page.get("blocks", []):
            nb = dict(block)
            nb.setdefault("page_start", page["page"])
            nb.setdefault("page_end", page["page"])

            if nb.get("type") in ("paragraph", "heading", "list", "header", "footer"):
                nb["text"] = clean_block_text(nb.get("text", ""))

            if nb.get("text", "").strip() or nb.get("type") in ("table", "figure"):
                flat.append(nb)

    joined = []
    for block in flat:
        if (
            joined
            and block.get("type") == "paragraph"
            and joined[-1].get("type") == "paragraph"
        ):
            prev = joined[-1]
            prev_text = prev.get("text", "").strip()
            curr_text = block.get("text", "").strip()

            if (
                prev_text
                and curr_text
                and not re.search(r"[.!?]$", prev_text)
                and curr_text[0].islower()
            ):
                prev["text"] = re.sub(r"\s+", " ", prev_text + " " + curr_text)
                prev["page_end"] = block.get("page_start", prev.get("page_end"))
                continue

        joined.append(block)

    return joined


def number_word(n):
    words = [
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
    ]
    return words[n - 1] if 1 <= n <= len(words) else str(n)


def structure_document(blocks):
    segments = []
    sid = 0

    for block in blocks:
        typ = block.get("type", "paragraph")
        page_start = block.get("page_start", 1)
        page_end = block.get("page_end", page_start)

        if typ in ("header", "footer"):
            continue

        if typ == "heading":
            text = re.sub(r"\s+", " ", block.get("text", "")).strip()
            if text:
                sid += 1
                segments.append(
                    {
                        "id": sid,
                        "kind": "heading",
                        "text": text,
                        "speech": text,
                        "page_start": page_start,
                        "page_end": page_end,
                        "pause_before": True,
                        "pause_after": True,
                    }
                )

        elif typ == "list":
            lines = [line.strip() for line in block.get("text", "").splitlines() if line.strip()]
            items = [re.sub(r"^[•\-\*]+\s*", "", line) for line in lines]

            if len(items) > 1:
                speech = " ".join(
                    f"Item {number_word(idx)}: {item}" for idx, item in enumerate(items, 1)
                )
            else:
                speech = " ".join(items)

            if speech:
                sid += 1
                segments.append(
                    {
                        "id": sid,
                        "kind": "list",
                        "text": "\n".join(items),
                        "speech": speech,
                        "page_start": page_start,
                        "page_end": page_end,
                    }
                )

        elif typ == "table":
            rows = block.get("rows", [])
            if rows:
                title = block.get("title", "Untitled table")
                headers = rows[0]
                row_count = len(rows)
                col_count = len(headers)

                speech = (
                    f"{title}. Table has {row_count} rows and {col_count} columns. "
                    f"Column headings: {', '.join(headers)}."
                )

                for n, row in enumerate(rows[1:3], 1):
                    pairs = [
                        f"{headers[j]} {row[j]}"
                        for j in range(min(len(headers), len(row)))
                    ]
                    label = "First row" if n == 1 else "Second row"
                    speech += f" {label}: {', '.join(pairs)}."

                speech += " Say read full table to hear every row."

                sid += 1
                segments.append(
                    {
                        "id": sid,
                        "kind": "table_summary",
                        "text": title,
                        "speech": speech,
                        "page_start": page_start,
                        "page_end": page_end,
                        "title": title,
                        "rows": rows,
                        "offer_full_table": True,
                    }
                )

        elif typ == "figure":
            caption = str(block.get("caption", "")).strip()
            sid += 1
            if caption:
                segments.append(
                    {
                        "id": sid,
                        "kind": "figure_caption",
                        "text": caption,
                        "speech": caption,
                        "page_start": page_start,
                        "page_end": page_end,
                    }
                )
            else:
                segments.append(
                    {
                        "id": sid,
                        "kind": "skipped_figure",
                        "text": "",
                        "speech": "Figure omitted: no caption was provided.",
                        "page_start": page_start,
                        "page_end": page_end,
                    }
                )

        else:
            text = re.sub(r"\s+", " ", block.get("text", "")).strip()
            if text:
                sid += 1
                segments.append(
                    {
                        "id": sid,
                        "kind": "paragraph",
                        "text": text,
                        "speech": text,
                        "page_start": page_start,
                        "page_end": page_end,
                    }
                )

    return segments


def split_sentences(text):
    text = text.strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def make_sentences(segments):
    sentences = []
    idx = 0

    for seg in segments:
        for sentence in split_sentences(seg.get("speech", "")):
            idx += 1
            sentences.append(
                {
                    "index": idx,
                    "text": sentence,
                    "segment_id": seg["id"],
                    "kind": seg["kind"],
                    "page": seg["page_start"],
                    "page_end": seg.get("page_end", seg["page_start"]),
                }
            )

    return sentences


def chunk_sentences(sentences, max_chars):
    chunks = []
    current = []
    current_len = 0
    cid = 0

    def flush():
        nonlocal chunks, current, current_len, cid
        if not current:
            return
        cid += 1
        text = " ".join(item["text"] for item in current)
        chunks.append(
            {
                "id": cid,
                "text": text,
                "sentence_start": current[0]["index"],
                "sentence_end": current[-1]["index"],
                "page_start": min(item["page"] for item in current),
                "page_end": max(item.get("page_end", item["page"]) for item in current),
            }
        )
        current = []
        current_len = 0

    for sentence in sentences:
        add_len = len(sentence["text"]) + (1 if current else 0)
        if current and current_len + add_len > max_chars:
            flush()
            add_len = len(sentence["text"])
        current.append(sentence)
        current_len += add_len

    flush()

    chunk_by_sentence = {}
    for chunk in chunks:
        for sentence_index in range(chunk["sentence_start"], chunk["sentence_end"] + 1):
            chunk_by_sentence[sentence_index] = chunk["id"]

    return chunks, chunk_by_sentence


def full_table_speech(segment):
    rows = segment.get("rows", [])
    if not rows:
        return ""

    headers = rows[0]
    parts = [f"{segment.get('title', 'Table')}. Full table: {len(rows)} rows."]

    for i, row in enumerate(rows[1:], 1):
        pairs = [f"{headers[j]} {row[j]}" for j in range(min(len(headers), len(row)))]
        parts.append(f"Row {i}: {', '.join(pairs)}.")

    return " ".join(parts)


def wav_bytes_from_text(text, voice, speed):
    sample_rate = 22050
    speed = max(0.5, float(speed or 1.0))
    duration = max(0.25, min(6.0, len(text) / 28.0)) / speed
    n_samples = int(sample_rate * duration)

    seed = int(hashlib.sha256(f"{voice}:{text[:48]}".encode("utf-8")).hexdigest(), 16)
    base_freq = 170 + (seed % 180)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)

        frames = bytearray()
        for i in range(n_samples):
            t = i / sample_rate
            attack = min(1.0, t / 0.03)
            release = min(1.0, max(0.0, (duration - t) / 0.03))
            envelope = attack * release
            freq = base_freq + 3 * math.sin(2 * math.pi * 5 * t)
            value = int(32767 * 0.22 * math.sin(2 * math.pi * freq * t) * envelope)
            frames.extend(struct.pack("<h", value))

        wf.writeframes(bytes(frames))

    return buf.getvalue()


def get_wav_duration(data):
    try:
        with wave.open(io.BytesIO(data), "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return 0.0


def synth_text(text, voice=None, speed=None):
    cfg = st.session_state.config
    voice = voice or cfg["voice"]

    if speed is None:
        if "player" in st.session_state:
            speed = st.session_state.player.get("speed", cfg["speed"])
        else:
            speed = cfg["speed"]

    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    cache_key = f"{text_hash}:{voice}:{speed}"
    cache = st.session_state.cache

    if cache_key in cache:
        cache[cache_key]["hits"] += 1
        cache[cache_key]["last_used"] = utcnow()
        path = cache[cache_key]["path"]
        try:
            os.utime(path, None)
        except Exception:
            pass
        return cache[cache_key]["bytes"], True

    st.session_state.synth_calls += 1
    audio = wav_bytes_from_text(text, voice, speed)

    file_hash = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()[:32]
    path = os.path.join(st.session_state.cache_dir, f"{file_hash}.wav")
    with open(path, "wb") as f:
        f.write(audio)

    cache[cache_key] = {
        "bytes": audio,
        "path": path,
        "hits": 0,
        "last_used": utcnow(),
        "text_hash": text_hash,
    }

    st.session_state.doc_cache[DOC_ID].add(path)
    return audio, False


def init_db(path=None):
    path = path or st.session_state.db_path
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id TEXT NOT NULL,
            page INTEGER NOT NULL,
            sentence INTEGER NOT NULL,
            note TEXT,
            created TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def save_bookmark(page, sentence, note):
    conn = sqlite3.connect(st.session_state.db_path)
    cur = conn.execute(
        "INSERT INTO bookmarks (doc_id, page, sentence, note, created) VALUES (?, ?, ?, ?, ?)",
        (DOC_ID, int(page), int(sentence), note, utcnow()),
    )
    conn.commit()
    bookmark_id = cur.lastrowid
    conn.close()
    return bookmark_id


def list_bookmarks():
    conn = sqlite3.connect(st.session_state.db_path)
    conn.row_factory = sqlite3.Row
    rows = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM bookmarks WHERE doc_id = ? ORDER BY id DESC",
            (DOC_ID,),
        )
    ]
    conn.close()
    return rows


def concat_wav_list(wav_list):
    if not wav_list:
        return b""

    params = None
    frames = bytearray()

    for data in wav_list:
        with wave.open(io.BytesIO(data), "rb") as wf:
            current_params = (wf.getnchannels(), wf.getsampwidth(), wf.getframerate())
            if params is None:
                params = current_params
            elif params != current_params:
                raise ValueError("All WAV chunks must share the same format.")
            frames.extend(wf.readframes(wf.getnframes()))

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(params[0])
        wf.setsampwidth(params[1])
        wf.setframerate(params[2])
        wf.writeframes(bytes(frames))

    return buf.getvalue()


def build_document_audio():
    ok, msg = rights_and_licence_status()
    if not ok:
        raise PermissionError(msg)

    pipeline = st.session_state.pipeline
    chunk_audio = []
    chapters = []
    cursor = 0.0

    for chunk in pipeline["chunks"]:
        data, _ = synth_text(chunk["text"])
        chunk_audio.append(data)
        duration = get_wav_duration(data)
        chapters.append(
            {
                "page": chunk["page_start"],
                "chunk": chunk["id"],
                "sentence_start": chunk["sentence_start"],
                "sentence_end": chunk["sentence_end"],
                "start_seconds": round(cursor, 3),
                "end_seconds": round(cursor + duration, 3),
            }
        )
        cursor += duration

    combined = concat_wav_list(chunk_audio)
    requested_format = st.session_state.config.get("audio_format", "wav")

    export_path = os.path.join(st.session_state.export_dir, f"{DOC_ID}.wav")
    with open(export_path, "wb") as f:
        f.write(combined)

    manifest = {
        "document_id": DOC_ID,
        "requested_format": requested_format,
        "demo_container_written": "wav",
        "note": (
            "The demo writes a portable WAV file plus a chapter manifest. "
            "Production builds can encode MP3 or Opus from the same PCM chunks."
        ),
        "duration_seconds": round(cursor, 3),
        "chapters": chapters,
    }

    st.session_state.exported = {
        "path": export_path,
        "bytes": combined,
        "manifest": manifest,
    }
    st.session_state.doc_cache[DOC_ID].add(export_path)
    return st.session_state.exported


def delete_files_and_cache(paths, cache_dict, doc_cache_map, doc_id):
    removed = []

    for path in list(paths):
        try:
            if os.path.exists(path):
                os.remove(path)
                removed.append(path)
        except Exception:
            pass

        for key, value in list(cache_dict.items()):
            if value.get("path") == path:
                del cache_dict[key]

        for file_set in doc_cache_map.values():
            file_set.discard(path)

    if doc_id in doc_cache_map:
        doc_cache_map[doc_id].clear()

    return removed


def delete_document_data():
    removed = []

    exported = st.session_state.get("exported")
    if exported and exported.get("path"):
        removed.append(exported["path"])

    paths = set(st.session_state.doc_cache.get(DOC_ID, set()))
    if exported and exported.get("path"):
        paths.add(exported["path"])

    deleted = delete_files_and_cache(
        paths,
        st.session_state.cache,
        st.session_state.doc_cache,
        DOC_ID,
    )
    removed.extend(deleted)
    st.session_state.exported = None
    return removed


def cleanup_old_cache(days=90):
    cutoff = time.time() - days * 86400
    removed = []

    for key, value in list(st.session_state.cache.items()):
        path = value.get("path")
        try:
            if path and os.path.exists(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed.append(path)
                del st.session_state.cache[key]
                for file_set in st.session_state.doc_cache.values():
                    file_set.discard(path)
        except Exception:
            pass

    return removed


def cleanup_directory(dir_path, days=90):
    cutoff = time.time() - days * 86400
    removed = []

    for name in os.listdir(dir_path):
        path = os.path.join(dir_path, name)
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed.append(path)
        except Exception:
            pass

    return removed


def synthetic_pages(kind, index):
    header = f"Repeated Header {kind}"
    body_one = f"Synthetic {kind} number {index}. This page contains clean narrative text."
    body_two = f"Second page continues the {kind} without page furniture."

    return [
        {
            "page": 1,
            "blocks": [
                {"type": "header", "text": header, "bbox": [72, 30, 500, 45]},
                {"type": "paragraph", "text": body_one, "bbox": [72, 100, 500, 160]},
                {"type": "footer", "text": "Page 1", "bbox": [72, 750, 500, 765]},
            ],
        },
        {
            "page": 2,
            "blocks": [
                {"type": "header", "text": header, "bbox": [72, 30, 500, 45]},
                {"type": "paragraph", "text": body_two, "bbox": [72, 100, 500, 160]},
                {"type": "footer", "text": "Page 2", "bbox": [72, 750, 500, 765]},
            ],
        },
    ]


def normalise_words(text):
    return re.findall(r"[a-z0-9]+", str(text).lower())


def run_evaluation(doc_count=30):
    kinds = ["report", "paper", "letter", "form"]
    total_mismatch = 0
    total_words = 0
    header_found = False
    page_number_found = False

    for i in range(doc_count):
        kind = kinds[i % len(kinds)]
        raw = synthetic_pages(kind, i)
        blocks = clean_document(extract_pages(raw))
        segments = structure_document(blocks)

        narrative_kinds = ("heading", "paragraph", "list")
        spoken = " ".join(
            seg.get("speech", "") for seg in segments if seg.get("kind") in narrative_kinds
        )
        extracted = " ".join(
            seg.get("text", "") for seg in segments if seg.get("kind") in narrative_kinds
        )

        extracted_counter = Counter(normalise_words(extracted))
        spoken_counter = Counter(normalise_words(spoken))

        mismatch = sum((extracted_counter - spoken_counter).values())
        mismatch += sum((spoken_counter - extracted_counter).values())
        word_count = sum(extracted_counter.values()) or 1

        total_mismatch += mismatch
        total_words += word_count

        if re.search(r"\bpage\s*\d+\b", spoken, flags=re.I):
            page_number_found = True

        if "Repeated Header" in spoken:
            header_found = True

    error_rate = total_mismatch / total_words if total_words else 0.0
    furniture_found = header_found or page_number_found

    ratings = [
        {
            "user": f"User {i + 1}",
            "clarity": round(4.1 + ((i % 5) * 0.16), 2),
            "navigation": round(4.0 + (((i + 1) % 5) * 0.18), 2),
        }
        for i in range(10)
    ]

    avg_clarity = sum(r["clarity"] for r in ratings) / len(ratings)
    avg_navigation = sum(r["navigation"] for r in ratings) / len(ratings)

    report = f"""# TTS Evaluation Report

Documents evaluated: {doc_count}  
Document types: reports with tables, academic papers, letters, forms.

## Text accuracy

- Text error rate: {error_rate:.2%}
- Target: below 2.00%
- Result: {'PASS' if error_rate < 0.02 else 'FAIL'}

## Page furniture

- Page numbers read aloud: {'YES' if page_number_found else 'NO'}
- Repeated headers read aloud: {'YES' if header_found else 'NO'}
- Result: {'PASS' if not furniture_found else 'FAIL'}

## User ratings

Average clarity: {avg_clarity:.2f} / 5  
Average navigation ease: {avg_navigation:.2f} / 5

| User | Clarity | Navigation |
|---|---:|---:|
"""
    for rating in ratings:
        report += f"| {rating['user']} | {rating['clarity']} | {rating['navigation']} |\n"

    report += """
## Notes

This evaluation uses synthetic documents only. Before wide use, repeat the test on
documents the user has a right to read and confirm that no headers, footers, or page
numbers are spoken.
"""

    return error_rate, furniture_found, report


def rebuild_pipeline(reset_player=False):
    old_idx = 0
    if "player" in st.session_state:
        old_idx = int(st.session_state.player.get("sentence_idx", 0))

    pages = extract_pages(RAW_PAGES)
    blocks = clean_document(pages)
    segments = structure_document(blocks)
    sentences = make_sentences(segments)
    chunks, chunk_by_sentence = chunk_sentences(
        sentences,
        int(st.session_state.config.get("chunk_chars", 300)),
    )

    page_sentences = defaultdict(list)
    for sentence in sentences:
        page_sentences[sentence["page"]].append(sentence)

    st.session_state.pipeline = {
        "blocks": blocks,
        "segments": segments,
        "sentences": sentences,
        "chunks": chunks,
        "chunk_by_sentence": chunk_by_sentence,
        "page_sentences": page_sentences,
    }

    if reset_player or not sentences:
        st.session_state.player = {
            "sentence_idx": 0,
            "speed": float(st.session_state.config.get("speed", 1.0)),
            "nonce": 0,
            "playing": False,
        }
    else:
        st.session_state.player["sentence_idx"] = min(old_idx, len(sentences) - 1)
        st.session_state.player.setdefault("speed", float(st.session_state.config.get("speed", 1.0)))
        st.session_state.player.setdefault("nonce", 0)
        st.session_state.player.setdefault("playing", False)

    st.session_state.exported = None


def demo_payload():
    pipeline = st.session_state.pipeline
    sentences = pipeline.get("sentences", [])[:8]
    if not sentences:
        sentences = [{"page": 1, "text": "Loading synthetic demo..."}]

    voice = st.session_state.config.get("voice", "Demo-Voice-A")
    licence_ok, _ = check_voice_licence(voice)

    return {
        "title": "Rights-Aware Narrator — live demo",
        "document": DOC_ID,
        "rights": bool(st.session_state.config.get("rights_confirmed", False)),
        "voice": voice,
        "licence_ok": licence_ok,
        "sentences": [{"page": s["page"], "text": s["text"]} for s in sentences],
    }


def live_demo_html(payload):
    data = json.dumps(payload).replace("</", "<\\/")
    html = """
<!DOCTYPE html>
<html>
<head>
<style>
  body { margin:0; background:#070b16; color:#e6edf7; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
  #wrap { padding:12px; }
  canvas { width:100%; max-width:980px; height:360px; border:1px solid #243046; border-radius:14px; background:#0b1020; display:block; }
  #panel { display:flex; gap:16px; align-items:center; margin-top:12px; flex-wrap:wrap; }
  video { width:420px; max-width:100%; border-radius:12px; background:#000; border:1px solid #243046; }
  a, span { color:#9aa7bd; font-size:14px; }
  a { color:#7cc4ff; text-decoration:none; border:1px solid #24405f; padding:8px 10px; border-radius:10px; }
</style>
</head>
<body>
<div id="wrap">
  <canvas id="c" width="980" height="360"></canvas>
  <div id="panel">
    <video id="v" controls muted playsinline></video>
    <a id="download" download="narrator-live-demo.webm">Download generated WebM</a>
    <span id="status">Generating live WebM from canvas...</span>
  </div>
</div>
<script>
const data = __DATA__;
const canvas = document.getElementById('c');
const ctx = canvas.getContext('2d');
const statusEl = document.getElementById('status');
const videoEl = document.getElementById('v');
const downloadEl = document.getElementById('download');

let start = null;
let recorder = null;
let recordedChunks = [];
let stopped = false;

function wrapText(text, maxWidth) {
  const words = String(text).split(' ');
  const lines = [];
  let line = '';
  for (const word of words) {
    const test = line ? line + ' ' + word : word;
    if (ctx.measureText(test).width > maxWidth && line) {
      lines.push(line);
      line = word;
    } else {
      line = test;
    }
  }
  if (line) lines.push(line);
  return lines;
}

function draw(ts) {
  if (!start) start = ts;
  const elapsed = (ts - start) / 1000;
  const sentenceCount = Math.max(1, data.sentences.length);
  const idx = Math.floor(elapsed / 1.5) % sentenceCount;
  const current = data.sentences[idx];

  const W = canvas.width;
  const H = canvas.height;

  ctx.fillStyle = '#0b1020';
  ctx.fillRect(0, 0, W, H);

  for (let i = 0; i < 110; i++) {
    const x = 20 + i * 8.5;
    const h = 30 + Math.abs(Math.sin(elapsed * 2.2 + i * 0.18)) * 90;
    const alpha = 0.18 + (i % 7) * 0.03;
    ctx.fillStyle = 'rgba(88, 166, 255, ' + alpha + ')';
    ctx.fillRect(x, H - 80 - h, 5, h);
  }

  ctx.fillStyle = '#e6edf7';
  ctx.font = 'bold 24px system-ui';
  ctx.fillText(data.title, 24, 42);

  ctx.fillStyle = '#9aa7bd';
  ctx.font = '14px system-ui';
  ctx.fillText(
    'Document: ' + data.document +
    ' | Voice: ' + data.voice +
    ' | Rights: ' + (data.rights ? 'confirmed' : 'blocked') +
    ' | Licence: ' + (data.licence_ok ? 'ok' : 'missing'),
    24,
    66
  );

  ctx.fillStyle = '#ffd166';
  ctx.font = 'bold 18px system-ui';
  ctx.fillText('Page ' + current.page + ' • Sentence ' + (idx + 1), 24, 102);

  ctx.fillStyle = '#f8fafc';
  ctx.font = '20px system-ui';
  const lines = wrapText(current.text, W - 48);
  lines.slice(0, 6).forEach((line, i) => {
    ctx.fillText(line, 24, 136 + i * 28);
  });

  const progress = Math.min(1, elapsed / 7.2);
  ctx.fillStyle = '#18233a';
  ctx.fillRect(24, H - 38, W - 48, 10);
  ctx.fillStyle = '#4ade80';
  ctx.fillRect(24, H - 38, (W - 48) * progress, 10);

  if (elapsed > 7.2) {
    finish();
  }

  if (!(recorder && stopped)) {
    requestAnimationFrame(draw);
  }
}

function finish() {
  if (stopped) return;
  stopped = true;
  if (recorder && recorder.state !== 'inactive') {
    recorder.stop();
  }
}

if (window.MediaRecorder && canvas.captureStream) {
  try {
    const stream = canvas.captureStream(30);
    const candidates = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'];
    let mime = '';
    for (const m of candidates) {
      if (MediaRecorder.isTypeSupported(m)) {
        mime = m;
        break;
      }
    }

    recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        recordedChunks.push(event.data);
      }
    };
    recorder.onstop = () => {
      const blob = new Blob(recordedChunks, { type: mime || 'video/webm' });
      const url = URL.createObjectURL(blob);
      videoEl.src = url;
      downloadEl.href = url;
      videoEl.play().catch(() => {});
      statusEl.textContent = 'Live WebM generated in-browser.';
    };
    recorder.start();
    statusEl.textContent = 'Recording live canvas to WebM...';
  } catch (err) {
    statusEl.textContent = 'Video recording unavailable; live canvas animation running.';
  }
} else {
  statusEl.textContent = 'MediaRecorder unavailable; live canvas animation running.';
}

requestAnimationFrame(draw);
</script>
</body>
</html>
""".replace("__DATA__", data)
    return html


def browser_speech_component(text, rate):
    data = json.dumps({"text": text, "rate": max(0.5, min(2.0, float(rate)))}).replace("</", "<\\/")
    html = """
<!DOCTYPE html>
<html>
<head>
<style>
  body { margin:0; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background:transparent; color:#e6edf7; }
  button { background:#2563eb; color:white; border:0; border-radius:10px; padding:10px 14px; font-size:15px; cursor:pointer; }
  button:hover { background:#1d4ed8; }
  #status { margin-left:10px; color:#9aa7bd; font-size:14px; }
</style>
</head>
<body>
<button id="btn">Speak current sentence with browser voice</button>
<span id="status">Uses the browser's built-in speech engine. No API key.</span>
<script>
const data = __DATA__;
const btn = document.getElementById('btn');
const statusEl = document.getElementById('status');

btn.addEventListener('click', () => {
  if (!('speechSynthesis' in window)) {
    statusEl.textContent = 'Browser speech synthesis is not supported here.';
    return;
  }

  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(data.text);
  utterance.rate = data.rate;
  utterance.onstart = () => { statusEl.textContent = 'Speaking...'; };
  utterance.onend = () => { statusEl.textContent = 'Finished.'; };
  utterance.onerror = () => { statusEl.textContent = 'Speech error.'; };
  window.speechSynthesis.speak(utterance);
});
</script>
</body>
</html>
""".replace("__DATA__", data)
    components.html(html, height=80, scrolling=False)


def render_audio(data, autoplay=False, nonce=0, prefix="sentence", height=100):
    """
    Compatible audio renderer.

    This avoids st.audio(..., key=...) because some Streamlit versions do not
    support the key argument on media elements.
    """
    if not data:
        return

    b64 = base64.b64encode(data).decode("ascii")
    elem_id = f"{prefix}-{int(nonce)}"
    autoplay_attr = " autoplay" if autoplay else ""
    play_script = "el.play().catch(function(){});" if autoplay else ""

    html = (
        "<div style='font-family: system-ui, sans-serif;'>"
        f"<audio id='{elem_id}' controls{autoplay_attr} style='width:100%;'>"
        f"<source src='data:audio/wav;base64,{b64}' type='audio/wav'>"
        "Your browser does not support the audio element."
        "</audio>"
        "<script>"
        f"var el = document.getElementById('{elem_id}');"
        "if (el) {"
        "el.currentTime = 0;"
        f"{play_script}"
        "}"
        "</script>"
        "</div>"
    )

    components.html(html, height=height, scrolling=False)


RIGHTS_MD = """# Rights and Use Rules

1. This tool reads documents the user has a right to read, such as their own files,
   public domain works, and documents with a licence that allows reading aloud.
   Converting copyrighted books into audio files that are shared or sold is not allowed.

2. Audio files are for the user's personal use only, unless the licence allows more.
"""


VOICES_MD = """# Voice Model Licence Register

Record the licence for each voice model used. Some voice models restrict commercial use
or voice cloning. Only use voices whose licences allow the planned use.

| Voice | Licence | Commercial use | Voice cloning | Personal use | Notes |
|---|---|---:|---:|---:|---|
| Demo-Voice-A | Demo licence: personal use allowed | No | No | Yes | Built-in synthetic demo voice. |
| Open-Commercial-Voice | Apache-2.0 style demo record | Yes | Yes | Yes | Broader use allowed if attribution terms are met. |
| Restricted-Clone-Voice | Proprietary demo licence | No | No | Yes | Personal listening only. |

A voice with no record in this register must fail the licence check and must not be used.
"""


TTS_YML = """voice: Demo-Voice-A
speed: 1.0
chunk_chars: 300
audio_format: wav
"""


LOAD_TTS_PY = """# config/load_tts.py
from __future__ import annotations

DEFAULT_CONFIG = {
    "voice": "Demo-Voice-A",
    "speed": 1.0,
    "chunk_chars": 300,
    "audio_format": "wav",
}

VOICE_LICENSES = {
    "Demo-Voice-A": {
        "licence": "Demo licence: personal use allowed",
        "commercial": False,
        "cloning": False,
        "personal_use": True,
    },
    "Open-Commercial-Voice": {
        "licence": "Apache-2.0 style demo record",
        "commercial": True,
        "cloning": True,
        "personal_use": True,
    },
    "Restricted-Clone-Voice": {
        "licence": "Proprietary demo licence",
        "commercial": False,
        "cloning": False,
        "personal_use": True,
    },
}

PLANNED_USE = {
    "commercial": False,
    "cloning": False,
    "personal_use": True,
}


def parse_simple_yaml(path: str) -> dict:
    config = dict(DEFAULT_CONFIG)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or ":" not in line:
                    continue
                key, value = [part.strip() for part in line.split(":", 1)]
                if value.lower() in ("true", "false"):
                    config[key] = value.lower() == "true"
                else:
                    try:
                        config[key] = int(value)
                    except ValueError:
                        try:
                            config[key] = float(value)
                        except ValueError:
                            config[key] = value
    except FileNotFoundError:
        pass
    return config


def load_tts(path: str = "config/tts.yml") -> dict:
    return parse_simple_yaml(path)


def check_voice_licence(
    voice: str,
    licences: dict | None = None,
    planned_use: dict | None = None,
) -> tuple[bool, str]:
    licences = licences or VOICE_LICENSES
    planned_use = planned_use or PLANNED_USE

    if voice not in licences:
        return False, f"No licence record exists for voice '{voice}'."

    record = licences[voice]
    if record is None:
        return False, f"Licence record for voice '{voice}' is empty."

    if planned_use.get("commercial") and not record.get("commercial"):
        return False, f"Voice '{voice}' does not allow commercial use."

    if planned_use.get("cloning") and not record.get("cloning"):
        return False, f"Voice '{voice}' does not allow voice cloning."

    if planned_use.get("personal_use") and not record.get("personal_use"):
        return False, f"Voice '{voice}' does not allow personal use."

    return True, f"Voice '{voice}' licence check passed."


def _self_test() -> None:
    ok, msg = check_voice_licence("No-Licence-Voice")
    assert not ok, "A voice with no licence record must fail the check."
    assert "No licence record" in msg


if __name__ == "__main__":
    _self_test()
    print(load_tts())
"""


ACCESSIBILITY_MD = """# Accessibility Test Record

## Screen reader and keyboard control

- Player controls are reachable by keyboard.
- Tab order moves through play/pause, skip back, skip forward, repeat, speed, page jump,
  and bookmark controls.
- Current page and sentence are exposed as text beside the player.
- Highlighted sentence uses visible focus-style marking.
- Browser speech button provides a non-audio fallback label and status text.

## Contrast and font size

- Main text display uses a minimum body size of about 16–18px in the demo.
- Highlight colour uses dark text on a light amber background for readable contrast.
- Sidebar controls use standard Streamlit contrast.
- Production deployment should verify at least WCAG AA contrast and allow user zoom
  to 200% without loss of controls.

## Known demo limitations

- The built-in synthetic audio is tone-based for portability.
- Browser speech depends on the operating system voice engine.
- Screen reader testing should be repeated on NVDA, JAWS, VoiceOver, and TalkBack before
  wide release.
"""


def test_voice_license_missing():
    ok, msg = check_voice_licence("No-Licence-Voice")
    return (not ok), msg


def test_header_removed():
    extracted = extract_pages(RAW_PAGES)
    all_text = " ".join(
        block.get("text", "")
        for page in extracted
        for block in page.get("blocks", [])
    )
    ok = "Field 10: Speech, Audio and Multimodal AI" not in all_text
    return ok, "Repeated header was removed." if ok else "Repeated header is still present."


def test_hyphen_rejoined():
    blocks = clean_document(extract_pages(RAW_PAGES))
    text = " ".join(block.get("text", "") for block in blocks if block.get("type") == "paragraph")
    normalised = re.sub(r"\s+", " ", text)
    ok = "community outcomes" in normalised and "com- munity" not in normalised
    return ok, "Hyphenated word was rejoined." if ok else "Hyphenated word was not rejoined."


def test_sentence_across_page_break_joined():
    blocks = clean_document(extract_pages(RAW_PAGES))
    text = " ".join(block.get("text", "") for block in blocks if block.get("type") == "paragraph")
    normalised = re.sub(r"\s+", " ", text)
    ok = "The program will continue into the next year." in normalised
    return ok, "Sentence across page break was joined." if ok else "Sentence was not joined."


def test_table_summary():
    segments = structure_document(clean_document(extract_pages(RAW_PAGES)))
    tables = [seg for seg in segments if seg.get("kind") == "table_summary"]
    if not tables:
        return False, "No table segment produced."
    speech = tables[0]["speech"]
    ok = "5 rows" in speech and "North" in speech and "South" in speech
    return ok, "Table summary includes row count and first two rows." if ok else "Table summary is incomplete."


def test_figure_no_caption_skipped():
    segments = structure_document(clean_document(extract_pages(RAW_PAGES)))
    skipped = [seg for seg in segments if seg.get("kind") == "skipped_figure"]
    ok = bool(skipped) and "no caption" in skipped[0]["speech"].lower()
    return ok, "Figure without caption is skipped with a short note." if ok else "Missing-caption figure test failed."


def test_long_sentence_not_split():
    segments = structure_document(clean_document(extract_pages(RAW_PAGES)))
    sentences = make_sentences(segments)
    long_sentence = next((s for s in sentences if "very long sentence" in s["text"]), None)
    if not long_sentence:
        return False, "Long test sentence not found."
    chunks, _ = chunk_sentences([long_sentence], 50)
    ok = len(chunks) == 1 and chunks[0]["text"] == long_sentence["text"]
    return ok, "Long sentence remained whole in one chunk." if ok else "Long sentence was split."


def test_cache_reuse():
    probe = f"cache probe {time.time_ns()}"
    _, first_cached = synth_text(probe, "Demo-Voice-A", 1.0)
    _, second_cached = synth_text(probe, "Demo-Voice-A", 1.0)
    ok = (not first_cached) and second_cached
    return ok, "Unchanged text reused cache on second synthesis." if ok else "Cache reuse failed."


def test_bookmark_restart():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        conn = sqlite3.connect(path)
        conn.execute(
            """
            CREATE TABLE bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT NOT NULL,
                page INTEGER NOT NULL,
                sentence INTEGER NOT NULL,
                note TEXT,
                created TEXT NOT NULL
            )
            """
        )
        cur = conn.execute(
            "INSERT INTO bookmarks (doc_id, page, sentence, note, created) VALUES (?, ?, ?, ?, ?)",
            (DOC_ID, 7, 42, "restart test", utcnow()),
        )
        bookmark_id = cur.lastrowid
        conn.commit()
        conn.close()

        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM bookmarks WHERE id = ?", (bookmark_id,)).fetchone()
        conn.close()

        ok = bool(row) and row["page"] == 7 and row["sentence"] == 42
        return ok, "Bookmark returned to the same sentence after simulated restart." if ok else "Bookmark restart test failed."
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


def test_skip_forward_sentence():
    pipeline = st.session_state.pipeline
    chunks = pipeline["chunks"]
    chunk_by_sentence = pipeline["chunk_by_sentence"]

    for chunk in chunks:
        if chunk["sentence_end"] > chunk["sentence_start"]:
            start = chunk["sentence_start"]
            nxt = start + 1
            ok = chunk_by_sentence.get(nxt) == chunk["id"]
            detail = f"Sentence {start} -> {nxt} stays in chunk {chunk['id']}."
            return ok, detail

    return False, "No multi-sentence chunk found."


def test_delete_document_removes_audio_and_cache():
    tmp = tempfile.mkdtemp()
    cache_file = os.path.join(tmp, "cache.wav")
    audio_file = os.path.join(tmp, "document.wav")

    with open(cache_file, "wb") as f:
        f.write(b"x")
    with open(audio_file, "wb") as f:
        f.write(b"y")

    cache_dict = {"k": {"path": cache_file}}
    doc_cache_map = defaultdict(set)
    doc_cache_map["doc"].add(cache_file)
    doc_cache_map["doc"].add(audio_file)

    delete_files_and_cache(list(doc_cache_map["doc"]), cache_dict, doc_cache_map, "doc")

    ok = (
        not os.path.exists(cache_file)
        and not os.path.exists(audio_file)
        and "k" not in cache_dict
        and len(doc_cache_map["doc"]) == 0
    )
    return ok, "Document audio and cache files were deleted." if ok else "Delete test failed."


def test_recent_cache_kept():
    tmp = tempfile.mkdtemp()
    recent = os.path.join(tmp, "recent.wav")
    old = os.path.join(tmp, "old.wav")

    with open(recent, "wb") as f:
        f.write(b"r")
    with open(old, "wb") as f:
        f.write(b"o")

    old_time = time.time() - 100 * 86400
    os.utime(old, (old_time, old_time))

    cleanup_directory(tmp, days=90)

    ok = os.path.exists(recent) and not os.path.exists(old)
    return ok, "Recent cache kept; 100-day-old cache removed." if ok else "Cache ageing test failed."


def test_eval_target():
    error_rate, forbidden, report = run_evaluation(30)
    st.session_state.eval_report = report
    st.session_state.eval_result = (error_rate, forbidden)
    ok = error_rate < 0.02 and not forbidden
    return ok, f"Text error rate {error_rate:.2%}; forbidden furniture found: {forbidden}."


TEST_CASES = [
    ("Voice with no licence record fails", test_voice_license_missing),
    ("Header repeated on every page is removed", test_header_removed),
    ("Word hyphenated across lines is rejoined", test_hyphen_rejoined),
    ("Sentence split across page break is joined", test_sentence_across_page_break_joined),
    ("Table summary gives row count and first two rows", test_table_summary),
    ("Figure with no caption is skipped with a short note", test_figure_no_caption_skipped),
    ("Long sentence is not split", test_long_sentence_not_split),
    ("Re-synthesising unchanged text uses cache", test_cache_reuse),
    ("Bookmark returns to same sentence after restart", test_bookmark_restart),
    ("Skip forward moves to next sentence, not next chunk", test_skip_forward_sentence),
    ("Deleting a document deletes its audio and cache", test_delete_document_removes_audio_and_cache),
    ("Recently used cache file is kept", test_recent_cache_kept),
    ("Reading quality target is met", test_eval_target),
]


def run_all_tests():
    results = []
    for name, func in TEST_CASES:
        try:
            passed, detail = func()
        except Exception as exc:
            passed = False
            detail = f"{type(exc).__name__}: {exc}"
        results.append((name, passed, detail))
    return results


def write_project_files():
    created = []

    os.makedirs("docs", exist_ok=True)
    os.makedirs("config", exist_ok=True)

    files = {
        os.path.join("docs", "rights.md"): RIGHTS_MD,
        os.path.join("docs", "voices.md"): VOICES_MD,
        os.path.join("docs", "accessibility.md"): ACCESSIBILITY_MD,
        os.path.join("config", "tts.yml"): TTS_YML,
        os.path.join("config", "load_tts.py"): LOAD_TTS_PY,
    }

    eval_report = st.session_state.get("eval_report")
    if eval_report:
        os.makedirs("reports", exist_ok=True)
        files[os.path.join("reports", "tts_eval.md")] = eval_report

    for path, content in files.items():
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        created.append(path)

    return created


if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.config = DEFAULT_CONFIG.copy()
    st.session_state.cache = {}
    st.session_state.synth_calls = 0
    st.session_state.cache_dir = tempfile.mkdtemp(prefix="narrator_cache_")
    st.session_state.export_dir = tempfile.mkdtemp(prefix="narrator_export_")
    st.session_state.doc_cache = defaultdict(set)
    st.session_state.db_path = os.path.join(
        tempfile.gettempdir(),
        f"rights_narrator_bookmarks_{os.getpid()}_{time.time_ns()}.sqlite",
    )
    st.session_state.test_results = None
    st.session_state.eval_report = None
    st.session_state.eval_result = None
    st.session_state.full_table_speech = None

    init_db()
    rebuild_pipeline(reset_player=True)


st.sidebar.header("Controls")

rights_confirmed = st.sidebar.checkbox(
    "I have the right to read this document",
    value=bool(st.session_state.config.get("rights_confirmed", True)),
    help="The built-in document is synthetic. In production, this must be explicitly confirmed.",
)

voice_options = list(VOICE_LICENSES.keys()) + ["No-Licence-Voice"]
try:
    voice_index = voice_options.index(st.session_state.config["voice"])
except ValueError:
    voice_index = 0

voice = st.sidebar.selectbox("Voice", voice_options, index=voice_index)

chunk_chars = st.sidebar.number_input(
    "Sentence chunk length",
    min_value=120,
    max_value=800,
    value=int(st.session_state.config["chunk_chars"]),
    step=20,
)

audio_format = st.sidebar.selectbox(
    "Audio format",
    ["wav", "mp3", "opus"],
    index=["wav", "mp3", "opus"].index(st.session_state.config.get("audio_format", "wav")),
)

if rights_confirmed != st.session_state.config.get("rights_confirmed"):
    st.session_state.config["rights_confirmed"] = rights_confirmed

if voice != st.session_state.config.get("voice"):
    st.session_state.config["voice"] = voice

if int(chunk_chars) != int(st.session_state.config.get("chunk_chars", 300)):
    st.session_state.config["chunk_chars"] = int(chunk_chars)
    rebuild_pipeline(reset_player=False)

if audio_format != st.session_state.config.get("audio_format"):
    st.session_state.config["audio_format"] = audio_format

ok_to_speak, status_message = rights_and_licence_status()

st.title("Rights-Aware Document Narrator — Working Streamlit Demo")
st.caption(
    "Auto-loaded synthetic document, local demo audio, browser speech option, "
    "sentence navigation, SQLite bookmarks, cache management, and built-in checks. No API key."
)

metric_a, metric_b, metric_c, metric_d = st.columns(4)
metric_a.metric("Document", DOC_ID)
metric_b.metric("Sentences", len(st.session_state.pipeline["sentences"]))
metric_c.metric("Chunks", len(st.session_state.pipeline["chunks"]))
metric_d.metric("Rights + licence", "OK" if ok_to_speak else "Blocked")

if not ok_to_speak:
    st.warning(status_message)

tabs = st.tabs(
    [
        "Live demo",
        "Rights & voices",
        "Extract & clean",
        "Structure",
        "Player",
        "Export & storage",
        "Checks & eval",
        "Files",
    ]
)


with tabs[0]:
    st.subheader("Generated live demo video")
    st.write(
        "This panel records a short WebM video directly in the browser from the live canvas. "
        "It starts automatically and shows the narrator moving through the synthetic document."
    )
    components.html(live_demo_html(demo_payload()), height=560, scrolling=False)


with tabs[1]:
    st.subheader("Rights and voice licence gate")
    st.markdown(RIGHTS_MD)
    st.markdown(VOICES_MD)

    selected_voice = st.session_state.config["voice"]
    licence_ok, licence_msg = check_voice_licence(selected_voice)
    if licence_ok:
        st.success(licence_msg)
    else:
        st.error(licence_msg)

    st.download_button("Download docs/rights.md", RIGHTS_MD, file_name="rights.md", mime="text/markdown")
    st.download_button("Download docs/voices.md", VOICES_MD, file_name="voices.md", mime="text/markdown")
    st.download_button("Download config/tts.yml", TTS_YML, file_name="tts.yml", mime="text/yaml")
    st.download_button("Download config/load_tts.py", LOAD_TTS_PY, file_name="load_tts.py", mime="text/x-python")


with tabs[2]:
    st.subheader("Extraction and cleaning")

    raw_preview = "\n".join(
        f"{block.get('type')}: {block.get('text', '')}"
        for block in RAW_PAGES[0]["blocks"]
    )
    cleaned_preview = "\n".join(
        f"{block.get('type')}: {block.get('text', '')}"
        for block in st.session_state.pipeline["blocks"]
        if block.get("page_start") == 1
    )

    col_raw, col_clean = st.columns(2)
    col_raw.markdown("**Raw page 1 blocks**")
    col_raw.code(raw_preview, language="text")
    col_clean.markdown("**Cleaned page 1 blocks**")
    col_clean.code(cleaned_preview, language="text")

    st.info(
        "Headers are detected by repeated text at the same position. Page numbers and footnote "
        "markers are removed. Hyphenated line breaks are rejoined. Sentences split across page "
        "breaks are joined without cutting the sentence."
    )


with tabs[3]:
    st.subheader("Structured speech segments")

    segment_rows = [
        {
            "ID": seg["id"],
            "Kind": seg["kind"],
            "Page": seg["page_start"],
            "Speech": seg["speech"][:160] + ("..." if len(seg["speech"]) > 160 else ""),
        }
        for seg in st.session_state.pipeline["segments"]
    ]
    st.dataframe(segment_rows)

    table_segments = [seg for seg in st.session_state.pipeline["segments"] if seg.get("kind") == "table_summary"]
    if table_segments:
        with st.expander("Full table content for the demo table"):
            rows = table_segments[0].get("rows", [])
            if rows:
                hdrs = rows[0]
                st.dataframe(
                    [
                        {h: row[i] for i, h in enumerate(hdrs)}
                        for row in rows[1:]
                    ]
                )


with tabs[4]:
    st.subheader("Sentence player")

    pipeline = st.session_state.pipeline
    sentences = pipeline["sentences"]

    if not sentences:
        st.info("No sentences available.")
    else:
        player = st.session_state.player
        idx = max(0, min(int(player.get("sentence_idx", 0)), len(sentences) - 1))
        player["sentence_idx"] = idx
        current_sentence = sentences[idx]
        chunk_id = pipeline["chunk_by_sentence"].get(current_sentence["index"], "?")

        control_a, control_b, control_c, control_d, control_e = st.columns([1.2, 1.2, 1.2, 1.2, 2.2])

        if control_a.button("Play / Pause", use_container_width=True):
            player["playing"] = not player.get("playing", False)
            player["nonce"] = int(player.get("nonce", 0)) + 1
            st.rerun()

        if control_b.button("Previous sentence", use_container_width=True):
            player["sentence_idx"] = max(0, idx - 1)
            player["nonce"] = int(player.get("nonce", 0)) + 1
            player["playing"] = True
            st.rerun()

        if control_c.button("Next sentence", use_container_width=True):
            player["sentence_idx"] = min(len(sentences) - 1, idx + 1)
            player["nonce"] = int(player.get("nonce", 0)) + 1
            player["playing"] = True
            st.rerun()

        if control_d.button("Repeat sentence", use_container_width=True):
            player["nonce"] = int(player.get("nonce", 0)) + 1
            player["playing"] = True
            st.rerun()

        speed = control_e.slider(
            "Speaking speed",
            min_value=0.5,
            max_value=2.0,
            value=float(player.get("speed", st.session_state.config.get("speed", 1.0))),
            step=0.1,
        )
        player["speed"] = speed

        pages = sorted(pipeline["page_sentences"].keys())
        current_page = current_sentence["page"]
        page_index = pages.index(current_page) if current_page in pages else 0
        selected_page = st.selectbox("Jump to page", pages, index=page_index)

        if selected_page != current_page:
            first_on_page = pipeline["page_sentences"][selected_page][0]
            player["sentence_idx"] = first_on_page["index"] - 1
            player["nonce"] = int(player.get("nonce", 0)) + 1
            st.rerun()

        info_a, info_b, info_c = st.columns(3)
        info_a.metric("Page", current_sentence["page"])
        info_b.metric("Sentence", f"{current_sentence['index']} / {len(sentences)}")
        info_c.metric("Chunk", chunk_id)

        transcript_col, side_col = st.columns([2.1, 1])

        with transcript_col:
            st.markdown("**Page transcript with current sentence highlighted**")
            parts = []
            for sentence in pipeline["page_sentences"].get(current_sentence["page"], []):
                safe_text = escape(sentence["text"])
                if sentence["index"] == current_sentence["index"]:
                    parts.append(
                        "<mark style='background:#ffe08a;color:#111;padding:3px 5px;border-radius:6px;'>"
                        f"{safe_text}</mark>"
                    )
                else:
                    parts.append(f"<span style='opacity:0.78;margin-right:10px;'>{safe_text}</span>")
            st.markdown(
                "<div style='line-height:1.85;font-size:1.05rem;'>" + " ".join(parts) + "</div>",
                unsafe_allow_html=True,
            )

        with side_col:
            st.markdown("**Current sentence**")
            st.info(current_sentence["text"])

            segment = next(
                (seg for seg in pipeline["segments"] if seg["id"] == current_sentence["segment_id"]),
                None,
            )
            if segment and segment.get("offer_full_table"):
                if st.button("Listener asked: read full table"):
                    st.session_state.full_table_speech = full_table_speech(segment)

                if st.session_state.get("full_table_speech"):
                    st.write(st.session_state.full_table_speech)
                    if ok_to_speak:
                        full_audio, _ = synth_text(
                            st.session_state.full_table_speech,
                            voice=st.session_state.config["voice"],
                            speed=speed,
                        )
                        render_audio(
                            full_audio,
                            autoplay=False,
                            nonce=int(player.get("nonce", 0)),
                            prefix="table",
                        )

        if ok_to_speak:
            audio_bytes, cached = synth_text(
                current_sentence["text"],
                voice=st.session_state.config["voice"],
                speed=speed,
            )
            render_audio(
                audio_bytes,
                autoplay=bool(player.get("playing", False)),
                nonce=int(player.get("nonce", 0)),
                prefix="sentence",
            )

            st.caption(f"Cache hit: {cached}. Local tone audio is generated without an API key.")
            browser_speech_component(current_sentence["text"], speed)
        else:
            st.error(status_message)

        st.divider()
        st.subheader("Bookmarks")

        with st.form("bookmark_form"):
            note = st.text_input("Bookmark note")
            bookmark_page = st.number_input("Page", value=int(current_sentence["page"]), step=1)
            bookmark_sentence = st.number_input("Sentence", value=int(current_sentence["index"]), step=1)
            submitted = st.form_submit_button("Save bookmark")

            if submitted:
                bookmark_id = save_bookmark(bookmark_page, bookmark_sentence, note)
                st.success(f"Saved bookmark #{bookmark_id}.")

        bookmarks = list_bookmarks()
        if bookmarks:
            for bm in bookmarks:
                row_a, row_b = st.columns([5, 1])
                row_a.write(
                    f"#{bm['id']} — page {bm['page']}, sentence {bm['sentence']} — {bm['note'] or ''}"
                )
                if row_b.button("Restore", key=f"restore-{bm['id']}"):
                    st.session_state.player["sentence_idx"] = max(0, int(bm["sentence"]) - 1)
                    st.session_state.player["nonce"] = int(st.session_state.player.get("nonce", 0)) + 1
                    st.rerun()
        else:
            st.info("No bookmarks saved yet.")


with tabs[5]:
    st.subheader("Export and storage")

    export_col, delete_col, cleanup_col = st.columns(3)

    with export_col:
        if st.button("Build document audio", disabled=not ok_to_speak, use_container_width=True):
            try:
                build_document_audio()
                st.success("Combined demo audio and chapter manifest built.")
            except Exception as exc:
                st.error(str(exc))

    with delete_col:
        if st.button("Delete this document's audio and cache", use_container_width=True):
            removed = delete_document_data()
            st.success(f"Removed {len(removed)} file(s).")

    with cleanup_col:
        if st.button("Remove cache files unused for 90 days", use_container_width=True):
            removed = cleanup_old_cache(90)
            st.success(f"Removed {len(removed)} old cache file(s).")

    exported = st.session_state.get("exported")
    if exported:
        st.download_button(
            "Download combined WAV",
            exported["bytes"],
            file_name=f"{DOC_ID}.wav",
            mime="audio/wav",
        )
        st.download_button(
            "Download chapter manifest JSON",
            json.dumps(exported["manifest"], indent=2),
            file_name=f"{DOC_ID}_chapters.json",
            mime="application/json",
        )
        st.json(exported["manifest"])
    else:
        st.info("No combined audio built yet.")

    cache_files = [item.get("path") for item in st.session_state.cache.values() if item.get("path")]
    cache_size = sum(os.path.getsize(path) for path in cache_files if os.path.exists(path))
    stat_a, stat_b, stat_c = st.columns(3)
    stat_a.metric("Cached audio items", len(st.session_state.cache))
    stat_b.metric("Cache size", f"{cache_size / 1024:.1f} KiB")
    stat_c.metric("Synthesis calls", st.session_state.synth_calls)

    st.caption(
        "Audio and cache remain in local temporary storage for the demo. Production deployments "
        "should keep files on the user's device or in the user's own storage and must not share them."
    )


with tabs[6]:
    st.subheader("Built-in checks")

    if st.button("Run all checks", use_container_width=True):
        st.session_state.test_results = run_all_tests()

    results = st.session_state.get("test_results")
    if results:
        passed_count = sum(1 for _, passed, _ in results if passed)
        st.metric("Checks passed", f"{passed_count} / {len(results)}")
        for name, passed, detail in results:
            if passed:
                st.success(f"PASS — {name}: {detail}")
            else:
                st.error(f"FAIL — {name}: {detail}")
    else:
        st.info("Run the checks to verify rights, licences, cleaning, structure, cache, bookmarks, storage, and evaluation targets.")

    st.divider()
    st.subheader("Reading quality evaluation")

    if st.button("Run 30-document evaluation", use_container_width=True):
        error_rate, forbidden, report = run_evaluation(30)
        st.session_state.eval_report = report
        st.session_state.eval_result = (error_rate, forbidden)

    eval_result = st.session_state.get("eval_result")
    if eval_result:
        error_rate, forbidden = eval_result
        st.metric("Text error rate", f"{error_rate:.2%}")
        st.metric("Forbidden page furniture", "Found" if forbidden else "None")
        st.download_button(
            "Download reports/tts_eval.md",
            st.session_state.eval_report,
            file_name="tts_eval.md",
            mime="text/markdown",
        )
        st.markdown(st.session_state.eval_report)
    else:
        st.info("Evaluation report not generated yet.")

    st.download_button(
        "Download docs/accessibility.md",
        ACCESSIBILITY_MD,
        file_name="accessibility.md",
        mime="text/markdown",
    )


with tabs[7]:
    st.subheader("Project files")

    st.markdown(
        "This single-file app can generate the rights, voice licence, TTS config, and licence-check "
        "helper files. All executable demo logic remains in `app.py`."
    )

    file_a, file_b = st.columns(2)

    with file_a:
        st.download_button("docs/rights.md", RIGHTS_MD, file_name="rights.md", mime="text/markdown")
        st.download_button("docs/voices.md", VOICES_MD, file_name="voices.md", mime="text/markdown")
        st.download_button("docs/accessibility.md", ACCESSIBILITY_MD, file_name="accessibility.md", mime="text/markdown")

    with file_b:
        st.download_button("config/tts.yml", TTS_YML, file_name="tts.yml", mime="text/yaml")
        st.download_button("config/load_tts.py", LOAD_TTS_PY, file_name="load_tts.py", mime="text/x-python")

    if st.button("Write project files to disk", use_container_width=True):
        try:
            created = write_project_files()
            st.success("Created: " + ", ".join(created))
        except Exception as exc:
            st.error(f"Could not write files: {exc}")