import pandas as pd

df = pd.read_csv("data\inspections.csv")

df.columns
df.describe()
df.head(10)
df.__len__
df.shape

