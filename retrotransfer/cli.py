"""Optional command-line interface for servers without a desktop environment."""
import argparse
import getpass
import secrets
import sys
from pathlib import Path

from .client import FileClient
from .security import config_dir, ensure_certificates
from .server import FileServer


def main(argv=None):
    parser = argparse.ArgumentParser(description="RetroTransfer 98 CLI — TCP + TLS")
    sub = parser.add_subparsers(dest="command", required=True)
    srv = sub.add_parser("server", help="Start a file server")
    srv.add_argument("--root", required=True)
    srv.add_argument("--host", default="0.0.0.0")
    srv.add_argument("--port", type=int, default=8000)
    for action in ("list", "send", "get"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--host", required=True)
        cmd.add_argument("--port", type=int, default=8000)
        cmd.add_argument("--fingerprint", required=True)
        if action == "list":
            cmd.add_argument("--path", default="")
        elif action == "send":
            cmd.add_argument("source")
            cmd.add_argument("--remote-folder", default="")
        else:
            cmd.add_argument("path")
            cmd.add_argument("--into", default=".")
    args = parser.parse_args(argv)
    try:
        if args.command == "server":
            secret = getpass.getpass("Shared access key (at least 12 characters): ")
            server = FileServer(root=args.root, secret=secret, host=args.host,
                                port=args.port, log=print,
                                started=lambda fp, port: print("PORT:", port, "\nTLS SHA256:", fp, flush=True))
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                server.stop()
            if server.failure:
                raise server.failure
        else:
            secret = getpass.getpass("Shared access key: ")
            client = FileClient(args.host, args.port, secret, args.fingerprint)
            if args.command == "list":
                for entry in client.list_remote(args.path)["entries"]:
                    print(("[DIR]" if entry["type"] == "dir" else "     "), entry["name"])
            elif args.command == "send":
                print(client.upload(args.source, args.remote_folder))
            else:
                print(client.download(args.path, args.into))
    except (Exception, KeyboardInterrupt) as exc:
        print("[ERROR]", str(exc), file=sys.stderr)
        return 1
    return 0
