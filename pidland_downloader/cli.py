#!/usr/bin/env python3
"""
============
# LEGAL-INFO
============
# Disclaimer:
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    any later version.
    This script is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY.

# Copyright:
    2026 Massimo Fares, INGV - Italy <massimo.fares@ingv.it>; EIDA Italia Team, INGV - Italy  <adaisacd.ont@ingv.it>

# License:
    GPLv3

# Platform:
    Linux

# Author:
    Massimo Fares, INGV - Italy <massimo.fares@ingv.it>
"""

import os
import asyncio
import aiohttp
import aiofiles
import argparse
import json
import itertools
import time
from datetime import datetime
from collections import defaultdict
from obspy import read
from importlib.metadata import metadata


# -----------------------
# CONFIG (default)
# -----------------------
OUTPUT_ROOT = "./SDS"
MAX_CONCURRENT = 5
TIMEOUT = aiohttp.ClientTimeout(total=240)

# -----------------------
# Utils
# -----------------------
def parse_sds_name(filename):
    parts = filename.split(".")
    return parts[0], parts[1], parts[2], parts[3], parts[5]

def build_sds_path(root, net, sta, cha, year, filename):
    return os.path.join(root, year, net, sta, f"{cha}.D", filename)

# -----------------------
# Manifest Summary
# -----------------------
def summarize_manifest(items):
    nets = set()
    stas = set()
    chas = set()
    years = set()

    for item in items:
        name = item.get("name", "")
        try:
            net, sta, loc, cha, year = parse_sds_name(name)
            nets.add(net)
            stas.add(sta)
            chas.add(cha)
            years.add(year)
        except Exception:
            continue

    print(" MANIFEST SUMMARY")
    print("-------------------------")
    print(f" Files     : {len(items)}")
    print(f" Networks  : {len(nets)} -> {', '.join(sorted(nets))}")
    print(f" Stations  : {len(stas)} -> {', '.join(sorted(stas))}")
    print(f" Channels  : {len(chas)} -> {', '.join(sorted(chas))}")
    print(f" Years     : {', '.join(sorted(years))}")
    print("-------------------------\n")


# -----------------------
# Estimated size
# -----------------------
def estimate_size(items):

    total_seconds = 0

    for item in items:
        tc = item.get("temporalCoverage", {})
        start = tc.get("startDate")
        end = tc.get("endDate")

        if not start or not end:
            continue

        try:
            t0 = datetime.fromisoformat(start.replace("Z", ""))
            t1 = datetime.fromisoformat(end.replace("Z", ""))
            total_seconds += (t1 - t0).total_seconds()
        except Exception:
            continue

    #  empirical coefficient mSEED
    # ~100 bytes/sec
    bytes_est = total_seconds * 100

    # byte human readable
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_est < 1024:
            break
        bytes_est /= 1024

    print(f" Estimated size : ~{bytes_est:.2f} {unit}\n")

# -----------------------
# SAC converters
# -----------------------
def mseed_to_single_sac(mseed_path):
    st = read(mseed_path)
    st.merge(method=1, fill_value='interpolate')

    tr = st[0]

    net = tr.stats.network
    sta = tr.stats.station
    cha = tr.stats.channel
    year = tr.stats.starttime.strftime("%Y")
    jday = tr.stats.starttime.strftime("%j")

    sac_path = os.path.join(
        os.path.dirname(mseed_path),
        f"{net}.{sta}.{cha}.{year}.{jday}.SAC"
    )

    tr.write(sac_path, format="SAC")
    return [sac_path]


def mseed_to_sac(mseed_path):
    st = read(mseed_path)
    out_files = []

    for i, tr in enumerate(st):
        net = tr.stats.network
        sta = tr.stats.station
        cha = tr.stats.channel
        start = tr.stats.starttime.strftime("%Y.%j.%H%M%S")

        sac_path = os.path.join(
            os.path.dirname(mseed_path),
            f"{net}.{sta}.{cha}.{start}.{i}.SAC"
        )

        tr.write(sac_path, format="SAC")
        out_files.append(sac_path)

    return out_files

# -----------------------
# Progress bar
# -----------------------
def print_progress(done, total):
    width = 30
    ratio = done / total
    filled = int(width * ratio)

    bar = "#" * filled + "-" * (width - filled)
    percent = int(ratio * 100)

    print(f"\r Progress: [{bar}] {percent}% ({done}/{total})", end="", flush=True)

# -----------------------
# Spinner
# -----------------------
async def spinner(task):
    for c in itertools.cycle(["|", "/", "-", "\\"]):
        if task.done():
            break
        print(f"\r Fetching manifest... {c}", end="", flush=True)
        await asyncio.sleep(0.1)
    print("\r Fetching manifest... done")


# -----------------------
# Download
# -----------------------
async def download_item(session, sem, item, summary, args, progress):

    url = item["@id"]
    filename = item["name"]
    # -----------------------
    # Sub-slicing naming
    # -----------------------
    url = item["@id"]

    if "/start/" in url:
        try:
            parts = url.split("/start/")[1]
            start, rest = parts.split("/end/")
            end = rest.split("?")[0]

            # formato compatto (filesystem safe)
            start_tag = start.replace(":", "").replace("-", "")
            end_tag = end.replace(":", "").replace("-", "")

            filename = f"{filename}.slice_{start_tag}_{end_tag}"

        except Exception:
            filename = f"{filename}.slice"

    net, sta, loc, cha, year = parse_sds_name(filename)
    path = build_sds_path(OUTPUT_ROOT, net, sta, cha, year, filename)

    os.makedirs(os.path.dirname(path), exist_ok=True)

    if os.path.exists(path):
        summary[(net, sta)] += 1
        return f"SKIP {filename}"

    async with sem:
        try:
            async with session.get(url) as resp:
                resp.raise_for_status()

                async with aiofiles.open(path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(8192):
                        await f.write(chunk)

            # -----------------------
            # SAC conversion (optional)
            # -----------------------
            if args.sac:
                try:
                    if args.raw:
                        sac_files = mseed_to_sac(path)
                    else:
                        sac_files = mseed_to_single_sac(path)

                    for sf in sac_files:
                        print(f" SAC {sf}")

                except Exception as e:
                    print(f"❌ SAC error {filename}: {e}")

            summary[(net, sta)] += 1
            progress["done"] += 1
            print_progress(progress["done"], progress["total"])
            return f" {filename}"

        except Exception as e:
            progress["done"] += 1
            print_progress(progress["done"], progress["total"])
            return f" {filename} ({e})"

# -----------------------
# Plot mseed
# -----------------------
def plot_file(filepath):
    try:
        st = read(filepath)
        st.plot(method="fast")
    except Exception as e:
        print(f"❌ Plot error: {e}")


# -----------------------
# Plot cmd cli
# -----------------------
def plot_main():

    parser = argparse.ArgumentParser(description="PIDland plot tool")
    parser.add_argument("file", help="Waveform file (miniSEED or SAC)")
    args = parser.parse_args()

    plot_file(args.file)

# -----------------------
# MAIN (async)
# -----------------------
async def run(args):   # <-- rinominata


    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:

        if args.from_manifest:
            print(f" Loading manifest from file: {args.from_manifest}")
            with open(args.from_manifest) as f:
                crate = json.load(f)

        else:
            print(f" Fetching RO-Crate:\n{args.url}\n")
            start_time = time.time()

            fetch_task = asyncio.create_task(session.get(args.url))
            spin_task = asyncio.create_task(spinner(fetch_task))

            resp = await fetch_task
            await spin_task

            resp.raise_for_status()
            crate = await resp.json()

            elapsed = time.time() - start_time
            print(f" Manifest fetched in {elapsed:.2f}s\n")

            items = [x for x in crate["@graph"] if x.get("@type") == "MediaObject"]

            print(f" Found {len(items)} items\n")

            summarize_manifest(items)
            estimate_size(items)

            # save manifest if requested
            if args.manifest_only:
                with open(args.manifest_out, "w") as f:
                    json.dump(crate, f, indent=2)
                print(f" Manifest saved to {args.manifest_out}")
                return

        items = [x for x in crate["@graph"] if x.get("@type") == "MediaObject"]
        progress = {
            "done": 0,
            "total": len(items)
        }
        print(f" Found {len(items)} items\n")

        summary = defaultdict(int)
        sem = asyncio.Semaphore(args.concurrent)

        tasks = [
            download_item(session, sem, item, summary, args, progress)
            for item in items
        ]

        for coro in asyncio.as_completed(tasks):
            await coro
        print()

        print("\n SUMMARY\n")
        for (net, sta), count in sorted(summary.items()):
            print(f"{net}.{sta} -> {count} files")


# -----------------------
# CLI
# -----------------------
def parse_args():
    parser = argparse.ArgumentParser(description="PIDland downloader")

    parser.add_argument("url", nargs="?", help="Handle/DOI URL")

    parser.add_argument("--sac", action="store_true",
                        help="Enable SAC conversion")

    parser.add_argument("--raw", action="store_true",
                        help="Generate SAC per trace (no merge)")

    parser.add_argument("--concurrent", type=int, default=MAX_CONCURRENT,
                        help="Max concurrent downloads")

    parser.add_argument("--manifest-only", action="store_true",
                        help="Download only the RO-Crate manifest")

    parser.add_argument("--from-manifest", type=str,
                        help="Load RO-Crate manifest from local file")

    parser.add_argument("--manifest-out", default="manifest.json",
                        help="Output filename for manifest")

    parser.add_argument("--plot", metavar="FILE",
                        help="Plot a waveform file (miniSEED/SAC)")

    parser.add_argument("--info", action="store_true",
                        help="Show tool information and exit")

    return parser.parse_args()


# -----------------------
# MAIN wrapper (NUOVO)
# -----------------------
def main():
    args = parse_args()

    if args.info:

        meta = metadata("pidland-downloader")

        print(f"\n{meta['Name']}")
        print(f"Version: {meta['Version']}\n")

        print(meta.get("Summary", ""))

        print("\nAuthor:")
        print(meta.get("Author-email", "N/A"))

        print("\nProject:")
        print(meta.get("Home-page", "N/A"))

        print()
        return

    if not args.url and not args.from_manifest:
        print("Error: you must provide either a Handle/DOI URL or --from-manifest filename")
        exit(1)


    asyncio.run(run(args))


# -----------------------
# ENTRYPOINT
# -----------------------
if __name__ == "__main__":
    main()