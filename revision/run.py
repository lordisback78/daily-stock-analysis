#!/usr/bin/env python3
"""Lance l'application de révision.

    python3 revision/run.py                 # http://127.0.0.1:8765
    python3 revision/run.py --port 9000
    python3 revision/run.py --host 0.0.0.0  # accessible depuis le téléphone
"""
import argparse
import os
import sys
import threading
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from revision.server.app import serve  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Application de révision (flashcards, QCM, examens)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("REVISION_PORT", 8765)))
    parser.add_argument("--open", action="store_true", help="ouvre le navigateur au démarrage")
    args = parser.parse_args()

    if args.open:
        url = f"http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{args.port}"
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
