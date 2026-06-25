"""
Main POC sync script.

Usage:
    python sync.py --dry-run          # Show what would be archived, no changes
    python sync.py --archive          # Archive unmatched Google photos
    python sync.py --report           # Save full report to report.json
    python sync.py --limit 100        # Only fetch first N Google photos (for testing)
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich import print as rprint

load_dotenv(Path(__file__).parent / ".env")

from apple_photos import get_active_photos
from google_photos import authenticate, fetch_all_photos, archive_photos
from match import match_photos, summarize

console = Console()


def parse_args():
    parser = argparse.ArgumentParser(description="Sync Apple Photos deletions to Google Photos")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without making any changes")
    parser.add_argument("--archive", action="store_true", help="Archive unmatched Google photos")
    parser.add_argument("--report", action="store_true", help="Save full report to report.json")
    parser.add_argument("--limit", type=int, default=None, help="Limit Google Photos fetched (for testing)")
    parser.add_argument("--library", type=str, default=None, help="Path to Apple Photos library")
    parser.add_argument("--low-confidence", action="store_true", help="Include low-confidence matches in archive action")
    return parser.parse_args()


def main():
    args = parse_args()

    if not args.dry_run and not args.archive and not args.report:
        console.print("[yellow]No action specified. Use --dry-run, --archive, or --report.[/yellow]")
        console.print("Run with --help for usage.")
        sys.exit(0)

    # Step 1: Load Apple Photos
    console.print("\n[bold blue]Step 1: Loading Apple Photos library...[/bold blue]")
    try:
        with console.status("Reading Apple Photos metadata..."):
            apple_photos = get_active_photos(args.library)
        console.print(f"[green]✓[/green] Found {len(apple_photos):,} photos in Apple Photos")
    except Exception as e:
        console.print(f"[red]Error reading Apple Photos: {e}[/red]")
        console.print("Make sure you're running this on macOS with Photos access.")
        sys.exit(1)

    # Step 2: Authenticate with Google
    console.print("\n[bold blue]Step 2: Authenticating with Google Photos...[/bold blue]")
    try:
        creds = authenticate()
        console.print("[green]✓[/green] Google Photos authenticated")
    except Exception as e:
        console.print(f"[red]Error authenticating with Google: {e}[/red]")
        console.print("Check your GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env")
        sys.exit(1)

    # Step 3: Fetch Google Photos
    console.print("\n[bold blue]Step 3: Fetching Google Photos library...[/bold blue]")
    google_photos = []
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            task = progress.add_task("Fetching Google Photos...", total=None)

            def on_progress(count):
                progress.update(task, description=f"Fetched {count:,} Google photos...")

            google_photos = fetch_all_photos(creds, progress_callback=on_progress)

        if args.limit:
            google_photos = google_photos[:args.limit]
            console.print(f"[yellow]Limited to {args.limit} photos for testing[/yellow]")

        console.print(f"[green]✓[/green] Found {len(google_photos):,} photos in Google Photos")
    except Exception as e:
        console.print(f"[red]Error fetching Google Photos: {e}[/red]")
        sys.exit(1)

    # Step 4: Match
    console.print("\n[bold blue]Step 4: Matching photos...[/bold blue]")
    with console.status("Running matching algorithm..."):
        results = match_photos(google_photos, apple_photos)
    summary = summarize(results)

    # Step 5: Report
    console.print("\n[bold blue]Results[/bold blue]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Category", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("Action")

    table.add_row(
        "Total Google Photos",
        f"{summary['total_google']:,}",
        "",
    )
    table.add_row(
        "High confidence matches",
        f"{summary['high_confidence']:,}",
        "[green]Keep[/green]",
    )
    table.add_row(
        "Low confidence matches",
        f"{summary['low_confidence']:,}",
        "[yellow]Review recommended[/yellow]",
    )
    table.add_row(
        "Unmatched (not in Apple Photos)",
        f"{summary['unmatched']:,}",
        "[red]Would archive[/red]" if args.dry_run else "[red]Archive[/red]",
    )
    console.print(table)

    # Show sample unmatched
    if summary["unmatched_list"]:
        console.print("\n[bold]Sample unmatched Google photos (first 10):[/bold]")
        for r in summary["unmatched_list"][:10]:
            date_str = r.google_photo.creation_time.strftime("%Y-%m-%d") if r.google_photo.creation_time else "unknown date"
            console.print(f"  • {r.google_photo.filename} ({date_str})")

    # Show sample low confidence
    if summary["low"] and args.low_confidence:
        console.print("\n[bold yellow]Sample low-confidence matches (first 10):[/bold yellow]")
        for r in summary["low"][:10]:
            apple_name = r.apple_photo.original_filename if r.apple_photo else "?"
            console.print(f"  • Google: {r.google_photo.filename} → Apple: {apple_name} [{r.match_reason}]")

    # Step 6: Archive (if requested)
    if args.archive and not args.dry_run:
        to_archive = [r.google_photo.id for r in summary["unmatched_list"]]
        if args.low_confidence:
            to_archive += [r.google_photo.id for r in summary["low"]]

        if not to_archive:
            console.print("\n[green]Nothing to archive.[/green]")
        else:
            console.print(f"\n[bold red]Archiving {len(to_archive):,} photos in Google Photos...[/bold red]")
            confirm = input(f"Type 'yes' to confirm archiving {len(to_archive)} photos: ")
            if confirm.strip().lower() != "yes":
                console.print("[yellow]Aborted.[/yellow]")
                sys.exit(0)

            archive_results = archive_photos(creds, to_archive)
            console.print(f"[green]✓[/green] Archived {len(archive_results['success']):,} photos")
            if archive_results["failed"]:
                console.print(f"[red]Failed to archive {len(archive_results['failed']):,} photos[/red]")

    elif args.dry_run:
        console.print(f"\n[yellow]Dry run complete — no changes made.[/yellow]")
        console.print(f"Run with --archive to archive {summary['unmatched']:,} unmatched Google photos.")

    # Step 7: Save report
    if args.report:
        report = {
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_apple": len(apple_photos),
                "total_google": summary["total_google"],
                "high_confidence_matches": summary["high_confidence"],
                "low_confidence_matches": summary["low_confidence"],
                "unmatched_in_google": summary["unmatched"],
            },
            "unmatched": [
                {
                    "google_id": r.google_photo.id,
                    "filename": r.google_photo.filename,
                    "creation_time": r.google_photo.creation_time.isoformat() if r.google_photo.creation_time else None,
                }
                for r in summary["unmatched_list"]
            ],
            "low_confidence": [
                {
                    "google_id": r.google_photo.id,
                    "google_filename": r.google_photo.filename,
                    "apple_filename": r.apple_photo.original_filename if r.apple_photo else None,
                    "match_reason": r.match_reason,
                }
                for r in summary["low"]
            ],
        }
        report_path = Path(__file__).parent / "report.json"
        report_path.write_text(json.dumps(report, indent=2))
        console.print(f"\n[green]✓[/green] Report saved to {report_path}")


if __name__ == "__main__":
    main()
