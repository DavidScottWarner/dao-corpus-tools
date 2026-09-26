# DAO Corpus Tools

This repository is the companion code for a methodology paper on selecting DAOs for qualitative analysis using Snapshot governance data. The scripts download public Snapshot data and write spreadsheets and text files. They do not choose the sample. The eligibility rules, ranking, and screening were applied by hand.

The paper's five steps are:

1. Full enumeration of Snapshot spaces
2. Eligibility (verified, 20 or more proposals, and a proposal in the 12 months before data collection)
3. Stratum assignment
4. Ranking and screening
5. Collection and confirmation

## Data source

All data come from the public Snapshot Hub GraphQL API:

https://hub.snapshot.org/graphql

No API key is needed. Snapshot allows 100 requests per minute. The scripts pause between requests and retry a failed request a few times before moving on.

The full list of Snapshot spaces was collected on September 13, 2026. The proposal texts were retrieved on September 24, 2026.

## What is in this repository

### Scripts

**`space_fetcher.py`** — Steps 1 and 3. Downloads every Snapshot space and writes a dated spreadsheet in `output/`. For each space it records the name, categories, follower count, proposal count, vote count, and whether Snapshot marks the space as verified. It looks up the first category in `strata.csv` and writes a stratum. If the category is not in that file, the stratum is `Unlisted`.

**`last_proposal_date_fetcher.py`** — Step 2. Reads space IDs from `space_ids.txt` and asks Snapshot for each space's most recent proposal. It writes a dated spreadsheet in `output/` with the date, title, and a status of `ok`, `no proposals`, or `error`. That date is what was used to check whether a space had a proposal in the 12 months before data collection. The script does not apply the verified or 20-proposal rules itself. Those fields come from the spreadsheet produced by `space_fetcher.py`.

**`proposal_fetcher.py`** — Step 5. Reads the selected organizations from `spaces_to_fetch.csv` and downloads every proposal for those Snapshot spaces. It writes one text file per proposal, plus `corpus/manifest.csv` and `corpus/fetch_summary.csv`. Each text file has a short header (title, dates, choices, scores, quorum, vote count, Snapshot URL, and discussion link) and then the full proposal body. If Snapshot has no discussion link, the header says `discussion: none`. Short bodies are kept and marked as stubs in the manifest. They are not skipped.

Ranking and screening (step 4) were done by hand. There is no script for that step. `spaces_to_fetch.csv` is the list that remained after screening, and it is the input to collection.

### Data files

**`strata.csv`** — Step 3. A table that maps each Snapshot category to a stratum: Protocol and Infrastructure, Capital, Public Goods and Service, Social and Cultural, or Unassigned. `space_fetcher.py` reads this file when it runs. The mapping is not written into the script.

**`space_ids.txt`** — Step 2. A plain-text list of 851 Snapshot space IDs, one per line. These are the spaces Snapshot marked as verified in the September 13, 2026 space list. `last_proposal_date_fetcher.py` reads this file.

**`spaces_to_fetch.csv`** — Steps 4 and 5. The organizations selected for the proposal corpus, with columns `organization`, `space_id`, and `stratum`. Mutant Cats DAO has two space IDs and one organization name. `proposal_fetcher.py` reads this file when it runs.

**`requirements.txt`** — The one Python package these scripts need: `requests`.

## The corpus is not in this repository

`corpus/` is listed in `.gitignore`, so the proposal text files, `corpus/manifest.csv`, and `corpus/fetch_summary.csv` are not stored here. Running `proposal_fetcher.py` creates that folder again. Spreadsheets written by the other two scripts go in `output/`, which is also not stored in the repository.

If a proposal file already exists, `proposal_fetcher.py` leaves it in place and continues. To start collection over, delete `corpus/` before you run the script again.

## How to install and run

These scripts were tested with Python 3.14.

Download the repository, go into the folder, create a virtual environment, and install the one required package:

```bash
git clone https://github.com/DavidScottWarner/dao-corpus-tools.git
cd dao-corpus-tools
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

When the environment is on, the start of the Terminal prompt shows `(.venv)`. If you do not see that, run the `source` line again. To turn it off later, type `deactivate`.

Download the full space list (step 1). This writes `output/spaces_YYYY-MM-DD.csv`, using the date you run it:

```bash
python space_fetcher.py
```

Look up the latest proposal date for each ID in `space_ids.txt` (step 2). This writes `output/last_proposal_dates_YYYY-MM-DD.csv`:

```bash
python last_proposal_date_fetcher.py
```

Download the proposal corpus (step 5). This recreates `corpus/`:

```bash
python proposal_fetcher.py
```

To try the proposal download with only two proposals per space:

```bash
python proposal_fetcher.py --test 2
```

The space list is large, so `space_fetcher.py` usually takes a few minutes. `last_proposal_date_fetcher.py` takes longer, because it makes one request per line in `space_ids.txt`. `proposal_fetcher.py` takes longer still, because it downloads the full text of every proposal for the selected spaces.

## Authorship

Written by David Scott Warner (University of Pittsburgh) with AI assistance (Cursor and Claude).

## How to cite

DOI to be added.
