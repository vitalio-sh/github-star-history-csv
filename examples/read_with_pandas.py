"""Optional pandas example: run from the repository root with pandas installed."""
import pandas as pd

stars = pd.read_csv("examples/stars.csv", parse_dates=["week_start"])
print(stars.head())
