import os
import uuid
import shutil
import asyncio
import time
import datetime
import pytz
from io import BytesIO
from playwright.async_api import async_playwright
import pandas as pd

LIMIT_QUERY = 499

def recreate_folder(path):
    if os.path.exists(path):
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            raise ValueError("Path exists but is not a directory")
    os.makedirs(path)

async def get_data(browser, year, start_date, end_date):
    # Check if end_date is before start_date
    if end_date < start_date:
        raise ValueError("end_date cannot be before start_date")

    # Format and print the dates
    f_start_date = start_date.strftime("%d/%m/%Y")
    f_end_date = end_date.strftime("%d/%m/%Y")

    # Start page instance
    context = await browser.new_context()
    page = await context.new_page()

    # Web scraping
    await page.goto("https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml")
    await page.locator("[id^=\"tbBuscador\\:idFormBuscarProceso\\:j_idt\"][id$=\"_panel\"]").get_by_text("Obra", exact=True).dispatch_event("click")
    await page.locator("[id=\"tbBuscador\\:idFormBuscarProceso\\:anioConvocatoria_label\"]").click()
    await page.locator("[id=\"tbBuscador\\:idFormBuscarProceso\\:anioConvocatoria_panel\"]").get_by_text(year).click()
    await page.get_by_text("Búsqueda Avanzada").click()
    await page.locator("[id=\"tbBuscador\\:idFormBuscarProceso\\:dfechaInicio_input\"]").click()
    await page.locator("[id=\"tbBuscador\\:idFormBuscarProceso\\:dfechaInicio_input\"]").fill(f_start_date)
    await page.locator("[id=\"tbBuscador\\:idFormBuscarProceso\\:dfechaFin_input\"]").click()
    await page.locator("[id=\"tbBuscador\\:idFormBuscarProceso\\:dfechaFin_input\"]").fill(f_end_date)
    await page.get_by_role("button", name="Buscar").click()
    #await page.pause()

    # Wait for the filter
    #await page.locator("[id=\"tbBuscador\\:idFormBuscarProceso\\:dtProcesos_data\"]").filter(has_not_text="No se encontraron Datos").click()
    time.sleep(6)

    # Download the results
    async with page.expect_download() as download_info:
        await page.get_by_role("button", name="Exportar a Excel").click()
    download = await download_info.value
    filepath = f"./tmp/{uuid.uuid4()}.xls"
    await download.save_as(filepath)

    # Cleanup
    await page.close()
    await context.close()

    df = pd.read_excel(filepath)
    return df

async def query_data_recursive(browser, year, start_date, end_date):
    # Ensure the date range is valid
    if start_date > end_date:
        return pd.DataFrame()

    # Query data between start_date and end_date
    df = await get_data(browser, year, start_date, end_date)
    
    # DEBUG
    print(f"query_data_recursive: {start_date} {end_date} {len(df)}")

    if len(df) < LIMIT_QUERY or start_date == end_date:
        return df
    
    # Calculate a midpoint date within the range.
    delta_days = (end_date - start_date).days
    mid_date = start_date + datetime.timedelta(days=delta_days // 2)
    
    # To avoid potential infinite recursion if the split doesn't reduce the range,
    # make sure the midpoint is strictly before the end_date.
    if mid_date >= end_date:
        return df

    # Recursively query the two halves of the date range.
    left_df = await query_data_recursive(browser, year, start_date, mid_date)
    right_df = await query_data_recursive(browser, year, mid_date + datetime.timedelta(days=1), end_date)
    
    # Concatenate the results from the two halves.
    return pd.concat([left_df, right_df])

async def query_years_data(browser, year, current_date):
    given_year = int(year)
    results = []
    
    # Only proceed if given_year is less than or equal to current year
    if given_year > current_date.year:
        return pd.DataFrame()
    
    # 1. Process the given year in 15-day chunks
    # If the given year is the current year, query only until current_date,
    # otherwise query the full year (January 1 to December 31)
    start_date_given = datetime.date(given_year, 1, 1)
    end_date_given = current_date if given_year == current_date.year else datetime.date(given_year, 12, 31)
    
    cur_date = start_date_given
    while cur_date <= end_date_given:
        # Define a 15-day window (including cur_date)
        next_date = cur_date + datetime.timedelta(days=14)
        if next_date > end_date_given:
            next_date = end_date_given
        df_part = await query_data_recursive(browser, year, cur_date, next_date)
        results.append(df_part)
        # Move to the day after next_date for the next interval.
        cur_date = next_date + datetime.timedelta(days=1)
    
    # 2. Process each full year after the given year up to (but not including) the current year.
    for yr in range(given_year + 1, current_date.year):
        start_date_year = datetime.date(yr, 1, 1)
        end_date_year = datetime.date(yr, 12, 31)
        # *** Modification: Split full years into two halves to avoid periods >300 days ***
        mid_date = start_date_year + (end_date_year - start_date_year) // 2
        df_first_half = await query_data_recursive(browser, year, start_date_year, mid_date)
        df_second_half = await query_data_recursive(browser, year, mid_date + datetime.timedelta(days=1), end_date_year)
        results.append(pd.concat([df_first_half, df_second_half], ignore_index=True))

    # 3. Process the current year (if it's after the given year) from January 1 to today.
    if current_date.year > given_year:
        start_date_current = datetime.date(current_date.year, 1, 1)
        end_date_current = current_date
        # *** Modification: Split the current year if the period exceeds 300 days ***
        if (end_date_current - start_date_current).days + 1 > 300:
            mid_date = start_date_current + (end_date_current - start_date_current) // 2
            df_first_half = await query_data_recursive(browser, year, start_date_current, mid_date)
            df_second_half = await query_data_recursive(browser, year, mid_date + timedelta(days=1), end_date_current)
            df_current = pd.concat([df_first_half, df_second_half], ignore_index=True)
        else:
            df_current = await query_data_recursive(browser, year, start_date_current, end_date_current)
        results.append(df_current)

    # Combine all data into one DataFrame
    if results:
        return pd.concat(results, ignore_index=True)
    else:
        return pd.DataFrame()

async def main():
    recreate_folder("./tmp/")

    # Get date data
    timezone = pytz.timezone('America/Lima')
    now = datetime.datetime.now(timezone)
    current_date = now.date()

    async with async_playwright() as p:
        if os.environ.get("ENV") == "dev":
            browser = await p.chromium.launch(headless=False, args=['--ozone-platform=wayland'])
        else:
            browser = await p.chromium.launch(headless=True)

        #for year in [str(current_date.year - i) for i in range(1)]:
        for year in ["2022"]:
            df = await query_years_data(browser, year, current_date)
            print(df)
            df.to_excel(f"TABLE_{year}.xlsx", index=False)

        # Cleanup
        await browser.close()

    # Export data

asyncio.run(main())

