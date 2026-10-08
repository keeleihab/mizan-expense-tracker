# Mizan: personal expense tracker

A Streamlit app to record, analyze and visualize personal expenses in Moroccan dirhams (MAD).

## Features

- Add, edit, search, filter and delete expenses (with undo)
- Spending by category, monthly trends and weekday patterns
- Budget tracking with remaining amount, % used and warnings
- Auto-generated insights, such as a month-end forecast and how long your budget will last
- Data saved to CSV, with import and export
- Sample data generator for demos

## Run it locally

```
pip install -r requirements.txt
streamlit run mizan_app.py
```

## Note on the hosted demo

The online version stores data in a CSV file on the server. That file is shared by everyone
who opens the demo and resets when the app restarts, so don't enter real personal data there.

Built with Python, Streamlit, pandas, Altair and Matplotlib.
