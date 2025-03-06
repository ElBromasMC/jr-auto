import os
import shutil
import asyncio
import time
import datetime
from playwright.async_api import async_playwright
import pandas as pd

def recreate_folder(path):
    if os.path.exists(path):
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            raise ValueError("Path exists but is not a directory")
    os.makedirs(path)

async def main():
    recreate_folder("./tmp/")

    current_year = datetime.date.today().year
    years = [str(current_year - i) for i in range(4)]

    # Get data
    async with async_playwright() as p:
        if os.environ.get("ENV") == "dev":
            browser = await p.chromium.launch(headless=False, args=['--ozone-platform=wayland'])
        else:
            browser = await p.chromium.launch(headless=True)

        for year in years:
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto("https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml")
            await page.locator("[id^=\"tbBuscador\\:idFormBuscarProceso\\:j_idt\"][id$=\"_panel\"]").get_by_text("Obra", exact=True).dispatch_event("click")
            await page.locator("[id=\"tbBuscador\\:idFormBuscarProceso\\:anioConvocatoria_label\"]").click()
            await page.locator("[id=\"tbBuscador\\:idFormBuscarProceso\\:anioConvocatoria_panel\"]").get_by_text(year).click()
            await page.get_by_role("button", name="Buscar").click()
            await page.locator("[id=\"tbBuscador\\:idFormBuscarProceso\\:dtProcesos_data\"]").filter(has_not_text="No se encontraron Datos").click()
            time.sleep(3)
            async with page.expect_download() as download_info:
                await page.get_by_role("button", name="Exportar a Excel").click()
            download = await download_info.value
            await download.save_as("./tmp/" + f"{year}.xls")
            #await page.pause()
            # Cleanup
            await page.close()
            await context.close()
        await browser.close()

    # Filter data
    for year in years:
        df = pd.read_excel("./tmp/" + f"{year}.xls")
        df.to_excel("./tmp/" + f"TABLE_{year}.xlsx", index=False)

    # Export data

asyncio.run(main())

