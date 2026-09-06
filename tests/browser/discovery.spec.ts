import { test, expect } from '@playwright/test';

for (const width of [1440, 390]) {
  test(`search detail compare and verify at ${width}px`, async ({page}) => {
    await page.setViewportSize({width, height: 960});
    const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
    await page.goto('/?source=candidates&q=rtk.shell_output_proxy');
    await expect(page.locator('#detail h2')).toHaveText('RTK Shell Output Compression Proxy');
    await page.getByRole('button',{name:'Verify metadata'}).click();
    await expect(page.locator('.verification')).toHaveText('matched_metadata');
    await page.locator('.snippet a').first().click();
    await expect(page.getByRole('dialog',{name:'Source field'})).toBeVisible();
    await page.getByRole('button',{name:'Close source field'}).click();
    await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
    await expect.poll(()=>page.locator('img').evaluateAll(images=>images.every(i=>(i as HTMLImageElement).naturalWidth>0))).toBeTruthy();
    await page.screenshot({path:`.data/screenshots/detail-${width}.png`,fullPage:false});
    await page.locator('#query').fill('HTTP');await page.locator('#mode').selectOption('lexical');
    await page.getByRole('button',{name:'Search',exact:true}).click();
    await expect(page.locator('#results .result')).not.toHaveCount(0);
    const checks=page.locator('#results input[type=checkbox]');
    await checks.nth(0).check();await expect(page.locator('#compare')).toHaveText('Compare (1)');
    await checks.nth(1).check();await expect(page.locator('#compare')).toHaveText('Compare (2)');
    await page.locator('#compare').click();await expect(page.locator('#comparison')).toBeVisible();
    await page.screenshot({path:`.data/screenshots/compare-${width}.png`,fullPage:false});
    await page.getByRole('button',{name:'Close comparison'}).click();
    expect(errors).toEqual([]);
  });
}

test('hostile package text stays inert',async({page})=>{
  await page.route('**/v1/packages/**',async route=>{
    const response=await route.fetch();const body=await response.json();
    body.summary='<img src=x onerror="window.pwned=true">';
    await route.fulfill({json:body});
  });
  await page.goto('/?source=candidates&q=rtk.shell_output_proxy');
  await expect(page.locator('.detail-summary')).toContainText('<img');
  expect(await page.evaluate(()=>('pwned' in window))).toBeFalsy();
  await expect(page.locator('.detail-summary img')).toHaveCount(0);
});
