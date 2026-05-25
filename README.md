![](assets/img/banner.png)

# Citation Network Constructor

An automated pipeline that constructs, filters, and visualizes thematically interconnected academic publication networks using DOIs and network techniques. Built in Python and D3.js. Find real articles, no LLM hallucination. 

Try the [demo](https://zzzhehao.github.io/citation-network/SIA_network.html).

## How Does it Work

The input is really simple. A few paper DOIs from the topic you are trying to get into, they are treated as the *initial core papers*. 

The program looks at the publications cited by your inputs, which are called the *peripheral papers*. The "importance" of the peripheral papers will be evaluated by how well they are connected to the cores. Potential *secondary core papers* may be assigned, and the process will be repeated for the new cores until no more are found or the maximum number of iterations is reached. 

When the search is finished, the core and most adjacent peripheral papers will be mapped into a network, hopefully providing a bigger picture of the topic you are trying to get into. The network is visualized with D3.js, so you can click on them to view basic metadata or read them. 

I find the most valuable use of this is to find the real "cores" of the topic from just a few input papers. And to find more papers using that knowledge further. 

![](assets/img/demo-1.png)

## Get Started

### Disclaimer

This tool interfaces with the CrossRef and Semantic Scholar APIs. While internal safeguards are implemented to manage request volume, users are solely responsible for their API usage.

Excessive scraping can lead to temporary or permanent IP blocking by these service providers. Please act responsibly:

- Respect the rate limits of the respective APIs.
- Avoid running unnecessarily large recursive searches.
- Use this software at your own risk. The author assumes no liability for any service interruptions, API bans, or misuse of this software by third parties.

### Installation

1. Copy this repository:
    ```shell
    git clone https://github.com/zzzhehao/citation-network.git
    ```
2. Navigate to the repository directory:
    ```shell
    cd citation-network
    ```
3. Create a virtual environment: 
    ```shell
    python3 -m venv venv
    ```
4. Activate it: 

   Mac/Linux:
    ```shell
    source venv/bin/activate
    ```
   Windows:
    ```shell
    venv\Scripts\activate
    ```
5. Install dependencies: 
    ```shell
    pip install -r requirements.txt
    ```

### Input Methods

You must provide seed DOIs using one of the following methods:

* **Positional Arguments:** Provide DOIs separated by spaces.
  ```shell
  python3 main.py 10.1038/nature12373 10.1038/ncomms11901
  ```
* **--dois:** Provide DOIs as a single comma-separated string.
  ```shell
  python3 main.py --dois "10.1038/nature12373,10.1038/ncomms11901"
  ```
* **-i, --input:** Pass a `.txt` file (one DOI per line) or a `.bib` (BibTeX) file. 
  ```shell
  python3 main.py -i my_papers.bib
  ```

### Run the demo yourself

```python
python3 main.py -i example.bib --recursive-threshold 0.15 --penalty-factor 0.5 --core-award 0.05
```

### Export & Output Settings


| Option         | Description                                                      | Default       | Value |
| -------------- | ---------------------------------------------------------------- | ------------- | ----- |
| `--run-name`   | Customize the basename of output files                           | yyyyMMDD_hhmm | *Any* |
| `--output-dir` | Defines the folder where results are saved                       | `./output`    | *Any* |
| `--no-csv`     | Skip exporting the csv file containing all scrapped publications | *N/A*         | *N/A* |
| `--no-json`    | Skip exporting the raw json network structure                    | *N/A*         | *N/A* |


### Network Filtering & API Parameters

| Option               | Description                                                                                                                                                                                                                  | Default | Value     |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- | --------- |
| `--min-year`         | Drops any publication published before this year                                                                                                                                                                             | 2000    | *Integer* |
| `--max-results`      | The maximum number of cited/citing papers to request per API call per core paper. Exhaustive searches may cause massive API rate-limiting and generate cluttered graphs. Capping this targets the most relevant connections. | 50      | *Integer* |
| `--force-large-core` | By default, the program stops if you provide >50 initial seed papers to prevent API bans. Use this flag to override the safeguard.                                                                                           | *N/A*   | *N/A*     |
| `--network-filter`   | Controls how strongly the peripheral papers are filtered out in the final graphs. Higher values increase the score threshold for a peripheral to be included.                                                                | 0.2     | *Float*   |

### Recursive Expansion Logic

The tool recursively expands its search by turning highly interconnected peripheral papers into "Secondary Core" papers and deep-scraping their references. The algorithm evaluates a candidate paper's "Score" based on its topology. 

| Option                  | Description                                                                                                                                                                            | Default | Value           |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- | --------------- |
| `--max-iterations`      | How many deep-dive cycles the scraper should run.                                                                                                                                      | 5       | *Integer*       |
| `--peripheral-vote`     | The fractional score contribution of a non-core (peripheral) edge. Allows clusters of peripheral papers to surface a secondary core paper.                                             | 0.5     | *Float*         |
| `--recursive-threshold` | The baseline percentage of the *current* core network that a candidate paper's score must exceed to be upgraded to a Secondary Core paper.                                             | 0.25    | *Float*         |
| `--penalty-factor`      | Applies an asymptotic decay curve to prevent a "snowball effect" explosion in later iterations. It determines how much of the remaining gap to 100% is available after each iteration. | 0.2     | *Float*         |
| `--core-award`          | Apply extra points for peripheral papers connected to core papers based on the core paper's score. Adjust this value carefully.                                                        | 0.05    | *Float* (0-0.2) |


In general, if you want to find as many papers as you can, try to increase --penalty-factor, --core-award, or decrease --recursive-threshold. If the program complained about finding too many new cores, try to decrease --core-award, --penalty-factor, or increase --recursive-threshold. 

But please be aware, that there's no universal rule or values that work for every scenario. The best setting depends on how many input papers you have, and how tight they are really connected within the topic you are presenting with those initial papers. Simply throwing a bunch of papers with potentially irrelevant connections might lead to an overwhelming or little informative network. 

Generally, I recommend starting with the default values and adjusting them based on your specific use case. Usually core award should not exceed 0.1, otherwise the number of new cores probably will explode at certain point. If you get warning that new cores are too many, reduce the core award will solve most of the problems. 

### Display & Developer Flags

| Option        | Description                                                          |
| ------------- | -------------------------------------------------------------------- |
| `--no-report` | Disables the statistical operational report printed in the terminal. |
| `--verbose`   | Enables diagnostic Python logging.                                   |
| `--no-cache`  | Disables generating and using cached citation metrics.               |
