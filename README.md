# PIDLand Downloader

Simple command-line tool to download seismic waveform data from PID-Defined-Dataset (with DOI or Handle) and optionally convert it to SAC format.

---

## Features

* Download waveform data (miniSEED) from PID-Defined-Dataset (with DOI or Handle)
* Store data in SDS structure
* Optional conversion to SAC format
* Parallel (asynchronous) download for high performance
* **Temporal sub-slicing support (time-window extraction)**

---

## Installation

#### Check your pip version

```bash
pip --version
```

If your pip version is older than 22.0, please upgrade:

```bash
pip install -U pip
```

#### Clone and install

```bash
git clone https://github.com/INGV/pid-land-client.git
cd pid-land-client
pip install .
```

---

## Usage

### Basic download (miniSEED only)

```bash
pidland-fetch "<DOI or Handle>"
```

### Download + SAC conversion (merged, recommended)

```bash
pidland-fetch "<DOI or Handle>" --sac
```

### Download + SAC (raw traces, no merge)

```bash
pidland-fetch "<DOI or Handle>" --sac --raw
```

---

## Example

```bash
pidland-fetch "https://hdl.handle.net/11099/wf-select?urlappend=?q=/net/IV/sta/AC??/loc//cha/H??/start/2024-04-08/end/2024-04-10/asof/2025-01-01" --sac

pidland-fetch "https://doi.org/11099/wf-select?urlappend=?q=/net/IV/sta/AC??/loc//cha/H??/start/2024-04-08/end/2024-04-10/asof/2025-01-01" --sac
```

---

##  Time Slicing (Sub-Slicing)

The downloader supports **temporal sub-slicing**, allowing extraction of specific time windows from waveform data.

### Daily time window slicing

If the query includes **time information**, the resolver (PidLand Server) automatically applies a **daily slicing strategy**.

Example:

```text
start=2024-04-09T10:00:00  
end=2024-04-11T10:10:00
```

This is interpreted as:

```
2024-04-09 → 10:00–10:10  
2024-04-10 → 10:00–10:10  
2024-04-11 → 10:00–10:10  
```

Each day is sliced independently and only matching data are returned.

---

### Example with slicing

```bash
pidland-fetch "https://hdl.handle.net/11099/wf-select?urlappend=?q=/net/IV/sta/AC??/loc//cha/H??/start/2024-04-09T10:00:00/end/2024-04-11T10:10:00/asof/2025-01-01"
```

---

### Behavior

* Slicing is performed **server-side**
* Only data overlapping the requested time window are returned
* The downloader automatically retrieves **already sliced miniSEED data**
* No post-processing is required on the client side

---

### Notes on slicing

* If only dates are provided (no time), full-day data are returned
* If time is provided, slicing is applied per day
* Output files reflect only the requested time window

---

## Download options

The downloader works directly with PID-defined datasets (identified by DOI or Handle) and their associated RO-Crate manifests, enabling reproducible, shareable, and batch-oriented workflows.

* `--manifest-only`
  Fetches the RO-Crate manifest from the resolver (PidLand Server) and saves it locally without downloading any waveform data.

* `--manifest-out <file>`
  Specifies the output filename for the saved manifest (default: `manifest.json`).

* `--from-manifest <file>`
  Loads a previously saved manifest and downloads the corresponding data without querying the resolver again.

---

## Why this matters

These options allow you to separate **data discovery** from **data download**, which is particularly useful in scientific workflows.

Benefits include:

* **Reproducibility** – the same manifest can be reused to retrieve exactly the same dataset
* **Batch processing** – multiple manifests can be processed automatically in scripts or pipelines
* **Offline execution** – data can be downloaded later without re-running the discovery

This approach aligns with FAIR principles by making data access workflows more transparent and reusable.

---

## Example workflow

```bash
# Step 1: generate a manifest (discovery phase)
pidland-fetch "<URL>" --manifest-only --manifest-out myquery.json

# Step 2: download data (can be done later or on another machine)
pidland-fetch --from-manifest myquery.json
```

---

## Batch usage example

```bash
for m in manifests/*.json; do
    pidland-fetch --from-manifest "$m"
done
```

This allows processing large collections of queries in a controlled and automated way.

---

## Output Structure (SDS)

Downloaded data are stored following the SDS (SeisComP Data Structure):

```
SDS/
 └── YEAR/
     └── NET/
         └── STA/
             └── CHA.D/
                 ├── IV.STA..CHA.D.YEAR.DAY     (miniSEED)
                 └── NET.STA.CHA.YEAR.DAY.SAC  (optional)
```

---

## Notes

* SAC conversion is performed using ObsPy (fill_value='interpolate')
* By default, SAC files are merged into continuous daily traces
* Using `--raw` produces one SAC file per trace segment
* Output SAC quality depends on available metadata

---

## WF-Select Query Syntax

The `wf-select` PID-Defined-Dataset supports wildcard queries using the `?` character.

### Supported wildcards

* `?` matches a single character
* Can be used in:

  * station codes (`sta`)
  * channel codes (`cha`)

---

## Examples

### Exact match

```text
/net/IV/sta/ACER/cha/HNE/
```

### Station wildcard (recommended)

```text
/net/IV/sta/AC??/cha/HNE/
```

### Channel wildcard

```text
/net/IV/sta/ACER/cha/H??/
```

---

## Performance considerations

Wildcard queries can significantly impact performance.

### Recommended usage

* Keep wildcards at the **end of the string**
* Use as few wildcards as possible

✔ Good:

```text
sta=AC??
```

### Avoid leading wildcards

Bad:

```text
sta=?G??
```

---

## Best practices

* Always specify network (`net`)
* Use precise station codes when possible
* Limit time ranges (`start` / `end`)
* Avoid broad wildcard queries

---

## Example full query

```text
https://hdl.handle.net/11099/wf-select?urlappend=?q=/net/IV/sta/AC??/loc//cha/H??/start/2024-04-08/end/2024-04-10/asof/2025-01-01
```

---

## Requirements

* Python >= 3.9
* pip >= 22.0

---

## Dependencies

Installed automatically:

* aiohttp
* aiofiles
* obspy

---

## Updating the tool

```bash
cd ~/pidland-downloader
git pull
pip install --upgrade .
```

---

## Troubleshooting

```bash
pip install -U pip
pip uninstall pidland-downloader -y
rm -rf build *.egg-info
pip install --no-cache-dir .
```

---

## Authors

* Massimo Fares – ONT-INGV
* EIDA-ITALIA Team - ONT-INGV

---

## License

GPLv3
