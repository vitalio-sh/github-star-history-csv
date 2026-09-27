# Live example data

`stars.csv` is the complete output of a real anonymous CLI run for
`vitalio-sh/chatgpt-3.5-turbo` on September 27, 2026: 188 weekly rows plus a header.
It is not a fixture. The first bucket is February 26, 2023; the last is September
27, 2026. The final cumulative API total in this snapshot is 165.

The [capture manifest](../docs/demo-run.json) records the exact command, runtime,
exit code and SHA-256. The [transcript](../docs/demo.txt) and
[terminal SVG](../docs/demo.svg) come from that run. The independently captured
[API responses](../docs/api-evidence.json) let you verify the transformation.

Read the [CSV contract](../README.md#csv-contract) before interpreting timestamps.
The columns are `week_start,stars_cumulative,stars_added`. The cumulative count
includes the labelled week; it is not the count at its start.

Optional pandas example (requires an existing pandas installation):

```sh
python3 examples/read_with_pandas.py
```

The exporter's runtime and tests require only Python's standard library.
