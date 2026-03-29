#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import psycopg2
import psycopg2.extras
from text2vec import SentenceModel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-dsn", required=True)
    parser.add_argument(
        "--model-name",
        default="shibing624/text2vec-base-chinese",
        help="text2vec model name or local path",
    )
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    model = SentenceModel(args.model_name)

    conn = psycopg2.connect(args.db_dsn)
    conn.autocommit = False

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            sql = """
            select subject_key, embedding_text
            from theme_profile_ext
            where embedding_text is not null
              and trim(embedding_text) <> ''
              and embedding is null
            order by subject_key
            """
            if args.limit and args.limit > 0:
                sql += f" limit {args.limit}"
            cur.execute(sql)
            rows = cur.fetchall()

        if not rows:
            print("[INFO] 没有待写入 embedding 的记录。")
            return

        print(f"[INFO] 待处理: {len(rows)} 条")

        batch_size = args.batch_size
        total = 0

        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            texts = [r["embedding_text"] for r in batch]
            subject_keys = [r["subject_key"] for r in batch]

            # text2vec 返回 ndarray/list，统一转 python list
            embeddings = model.encode(texts)
            embeddings = [e.tolist() if hasattr(e, "tolist") else list(e) for e in embeddings]

            dim = len(embeddings[0]) if embeddings else 0
            print(f"[INFO] 批次 {start // batch_size + 1}: {len(batch)} 条, dim={dim}")

            if args.dry_run:
                print("[DRY-RUN] 本批仅编码，不写库。")
                total += len(batch)
                continue

            with conn.cursor() as cur:
                for sk, emb in zip(subject_keys, embeddings):
                    cur.execute(
                        """
                        update theme_profile_ext
                        set embedding = %s,
                            updated_at = now()
                        where subject_key = %s
                        """,
                        (emb, sk),
                    )
            conn.commit()
            total += len(batch)
            print(f"[INFO] 已写入: {total}")

        print(f"[DONE] 完成，共处理 {total} 条。")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()