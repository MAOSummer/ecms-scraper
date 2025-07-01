
import streamlit as st
import datetime
from scraper import run_scraper
import io

st.title("PennDOT ECMS Scraper")
st.markdown("""
Use this app to scrape publicly available agreement records from the Pennsylvania ECMS website.
Choose your date range and sources below.
""")

# --- Date range ---
st.subheader("Step 1: Select Year Range")
default_start = datetime.datetime.now().year - 1
default_end = datetime.datetime.now().year
start_year = st.number_input("Start Year", min_value=2000, max_value=default_end, value=default_start)
end_year = st.number_input("End Year", min_value=start_year, max_value=default_end, value=default_end)
st.caption(f"Note: The latest data available is through {default_end}.")

# --- Source selection ---
st.subheader("Step 2: Select Data Source(s)")
source_options = {
    "Executed Legal Agreements": "Standard agreement documents",
    "Executed Legal Supplements": "⚠️ Recommended max 2-year range (longer runtime)",
    "Executed Legal Work Orders": "Work orders tied to agreements",
    "Executed Legal Work Order Amendments": "Amendments to prior work orders"
}
selected_sources = st.multiselect(
    "Choose one or multiple:",
    options=list(source_options.keys()),
    format_func=lambda x: f"{x} ({source_options[x]})"
)

# --- Runtime estimates ---
st.subheader("Estimated Runtime by Source")
st.markdown("""
- **Executed Legal Agreements**: ~1 hour
- **Executed Legal Supplements**: ~3–4 hours (⚠️ longer if >2 years)
- **Executed Legal Work Orders**: ~1.5 hours
- **Work Order Amendments**: ~40 minutes
""")

# --- Run button ---
if st.button("Run Scraper"):
    if not selected_sources:
        st.warning("Please select at least one source to run.")
    else:
        st.success(f"Starting scraper for {', '.join(selected_sources)} from {start_year} to {end_year}...")
        results = run_scraper(start_year, end_year, selected_sources)

        for source_name, df in results:
            st.write(f"### {source_name} Results ({len(df)} records)")
            st.dataframe(df)

            towrite = io.BytesIO()
            df.to_excel(towrite, index=False, engine='openpyxl')
            towrite.seek(0)

            st.download_button(
                label=f"📥 Download {source_name}.xlsx",
                data=towrite,
                file_name=source_name.replace(" ", "_") + ".xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
