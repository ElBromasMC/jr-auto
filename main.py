import os
import sys
import subprocess
import uuid
import shutil
import asyncio
import time
import datetime
import pytz
import numpy as np
import openpyxl
from io import BytesIO
from playwright.async_api import async_playwright
import pandas as pd

LIMIT_QUERY = 499
MAIN_SHEET_NAME = "Data filtrada"
KEYWORDS = ["UNIVERSIDAD", "HOSPITAL", "COLEGIO"]

DATA_DIR  = os.environ.get("DATA_DIR", "./data")
TMP_DIR   = f"{DATA_DIR}/tmp"
QUERY_DIR = f"{DATA_DIR}/query"
DRIVE_DIR = f"{DATA_DIR}/Onedrive"
EXPORT_DIR = os.environ.get("EXPORT_DIR", "EXPORT")

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
    filepath = f"{TMP_DIR}/{uuid.uuid4()}.xls"
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
    print(f"MAIN: query_data_recursive: {start_date} {end_date} {len(df)}")

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

def filter_data(df):
    def convert_to_float(x):
        try:
            return float(x.replace(',', ''))
        except Exception:
            return np.nan

    # Drop the "N°" column.
    if "N°" in df.columns:
        df = df.drop("N°", axis=1)

    # Create a helper numeric column for filtering and sorting.
    df['valor_numeric'] = df["Valor Referencial / Valor Estimado"].apply(convert_to_float)

    # Filter the DataFrame:
    mask = (df['valor_numeric'] > 4000000) | (df['valor_numeric'].isna())
    df_filtered = df[mask].copy()

    # Sort the filtered DataFrame in descending order using the numeric column.
    # Rows with non-numeric values (i.e. NaN) will be placed at the end.
    df_sorted = df_filtered.sort_values(by='valor_numeric', ascending=False, na_position='first')

    # Replace "Valor Referencial / Valor Estimado" values with the numeric ones.
    #df_sorted["Valor Referencial / Valor Estimado"] = df_sorted['valor_numeric']
    # Optionally drop the helper column if no longer needed.
    df_sorted = df_sorted.drop('valor_numeric', axis=1)

    keyword_dfs = {}
    for keyword in KEYWORDS:
        keyword_dfs[keyword] = df_sorted[df_sorted["Descripción de Objeto"].str.contains(keyword, case=False, na=False)]

    return df_sorted, keyword_dfs

def prepare_data_for_excel(main_df, df_map, filter_filepath):
    if os.path.exists(filter_filepath):
        xls = pd.ExcelFile(filter_filepath)
        
        main_sheet_name = MAIN_SHEET_NAME.capitalize()
        if main_sheet_name in xls.sheet_names:
            existing_main_df = pd.read_excel(xls, main_sheet_name)
            new_main_rows = main_df[~main_df['Nomenclatura'].isin(existing_main_df['Nomenclatura'])]
            updated_main_df = pd.concat([existing_main_df, new_main_rows], ignore_index=True)
        else:
            updated_main_df = main_df
        for keyword in KEYWORDS:
            if keyword in df_map:
                kw_sheet_name = keyword.capitalize()
                if kw_sheet_name in xls.sheet_names:
                    existing_keyword_df = pd.read_excel(xls, kw_sheet_name)
                    new_keyword_rows = df_map[keyword][~df_map[keyword]['Nomenclatura'].isin(existing_keyword_df['Nomenclatura'])]
                    df_map[keyword] = pd.concat([existing_keyword_df, new_keyword_rows], ignore_index=True)
        return updated_main_df
    else:
        return main_df

def format_table(wb, sheetname, df, display_name):
    # Define styles
    style = openpyxl.worksheet.table.TableStyleInfo(name="TableStyleMedium9", showFirstColumn=False,
                           showLastColumn=False, showRowStripes=True, showColumnStripes=False)
    alignment = openpyxl.styles.Alignment(wrap_text=True, vertical='top', horizontal='center')
    width_dict = {
        "Descripción de Objeto": 60,
        "Nombre o Sigla de la Entidad": 40,
        "Valor Referencial / Valor Estimado": 30
    }

    # Apply the styles
    table = openpyxl.worksheet.table.Table(
        displayName=display_name,
        ref=f'A1:{openpyxl.utils.get_column_letter(df.shape[1])}{len(df)+1}'
    )
    table.tableStyleInfo = style
    wb[sheetname].add_table(table)

    # Set column widths based on column names
    for idx, col_name in enumerate(df.columns, start=1):
        col_letter = openpyxl.utils.get_column_letter(idx)
        width = width_dict.get(col_name, 25)
        wb[sheetname].column_dimensions[col_letter].width = width
    # Apply alignment to all cells in the table
    for row in wb[sheetname].iter_rows(min_row=1, max_row=len(df)+1, min_col=1, max_col=df.shape[1]):
        for cell in row:
            cell.alignment = alignment
    # Set row height to auto
    for row_num in range(2, len(df) + 2):
        wb[sheetname].row_dimensions[row_num].height = 90

def data_to_excel(df_sorted, keyword_dfs, output_file):
    # Export all DataFrames to an Excel file with each on a separate sheet.
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # Main filtered and sorted DataFrame.
        df_sorted.to_excel(writer, sheet_name=MAIN_SHEET_NAME, index=False)
        # Export each keyword-specific DataFrame.
        for keyword, df_kw in keyword_dfs.items():
            df_kw.to_excel(writer, sheet_name=keyword.capitalize(), index=False)

    # Format table
    wb = openpyxl.load_workbook(filename = output_file)
    format_table(wb, MAIN_SHEET_NAME, df_sorted, "Tabla")
    for keyword, df_kw in keyword_dfs.items():
        format_table(wb, keyword.capitalize(), df_kw, keyword.capitalize())
    wb.save(output_file)

async def main():
    if not os.path.isdir(DATA_DIR):
        raise FileNotFoundError(f"Directory {DATA_DIR} does not exist!")

    recreate_folder(TMP_DIR)
    recreate_folder(DRIVE_DIR)
    os.makedirs(QUERY_DIR, exist_ok=True)
    os.makedirs(f"{DRIVE_DIR}/{EXPORT_DIR}", exist_ok=True)

    # Import data
    if os.environ.get("INCREMENTAL") != "no":
        result = subprocess.run([
            "onedrive",
            "--sync",
            "--syncdir",
            DRIVE_DIR,
            "--single-directory",
            EXPORT_DIR,
            "--download-only",
            "--cleanup-local-files",
        ])
        if result.returncode != 0:
            sys.exit(result.returncode)

    # Get date data
    timezone = pytz.timezone('America/Lima')
    now = datetime.datetime.now(timezone)
    current_date = now.date()

    async with async_playwright() as p:
        if os.environ.get("ENV") == "dev":
            browser = await p.chromium.launch(headless=False, args=['--ozone-platform=wayland'])
        else:
            browser = await p.chromium.launch(headless=True)

        # TODO
        for year in [str(current_date.year - i) for i in range(4)]:
            print(f"MAIN: Starting data collection for year {year}.")
            export_filepath = f"{QUERY_DIR}/{year}.xlsx"
            filter_filepath = f"{DRIVE_DIR}/{EXPORT_DIR}/SEACE_OBRAS_{year}.xlsx"
            if os.path.exists(export_filepath) and year != str(current_date.year):
                print(f"MAIN: {export_filepath} already exists, skipping query.")
                df = pd.read_excel(export_filepath)
            else:
                df = await query_years_data(browser, year, current_date)
                df.to_excel(export_filepath, index=False)
            main_df, df_map = filter_data(df)
            main_df = prepare_data_for_excel(main_df, df_map, filter_filepath)
            data_to_excel(main_df, df_map, filter_filepath)

        # Cleanup
        await browser.close()

    # Export data
    result = subprocess.run([
        "onedrive",
        "--sync",
        "--syncdir",
        DRIVE_DIR,
        "--single-directory",
        EXPORT_DIR,
        "--upload-only",
        "--no-remote-delete",
    ])
    if result.returncode != 0:
        sys.exit(result.returncode)

asyncio.run(main())

