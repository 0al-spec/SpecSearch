import {test, expect} from '@playwright/test';

for(const width of [1440,390])test(`upstream survives discovery and comparison at ${width}px`,async({page})=>{
 await page.setViewportSize({width,height:960});
 const upstream={url:'https://github.com/openai/codex',revision:'16d7daad7c5dc73da8558102a65bb7d7709807e1'};
 const packages=['a','b'].map(id=>({record_id:id,package_id:`fixture.${id}`,version:'1.0.0',name:`Package ${id}`,summary:'Coding agent',source_kind:'registry',source_id:'fixture',license:'MIT',digest:id,details:{metadata:{source:{url:'https://registry.example/spec.tgz'}}},documents:[],evidence:[],provenance:{},upstream:id==='a'?upstream:null}));
 await page.route('**/v1/status',r=>r.fulfill({json:{packages:2}}));
 await page.route('**/v1/search',r=>r.fulfill({json:{snapshot:'fixture',mode:'lexical',latency_ms:1,results:packages.map(p=>({...p,source:p.source_kind,ranking_score:null,match_strength:'exact',snippets:[]}))}}));
 await page.route('**/v1/packages/**',r=>r.fulfill({json:packages.find(p=>new URL(r.request().url()).pathname.endsWith(p.record_id))}));
 await page.goto('/?q=coding');
 const link=page.locator('#detail').getByRole('link',{name:'Upstream project'});
 await expect(link).toHaveAttribute('href',upstream.url);
 await expect(link).toHaveAttribute('rel','noopener noreferrer');
 await expect(page.locator('#detail .upstream code')).toHaveText(upstream.revision);
 await expect(page.locator('#results').getByRole('link',{name:'Upstream project'})).toHaveCount(1);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.screenshot({path:`.data/screenshots/upstream-detail-${width}.png`,fullPage:true});
 await page.getByRole('checkbox',{name:'Compare fixture.a',exact:true}).check();
 await page.getByRole('checkbox',{name:'Compare fixture.b',exact:true}).check();
 await page.locator('#compare').click();
 await expect(page.locator('#comparison').getByRole('link',{name:'Upstream project'})).toHaveAttribute('href',upstream.url);
 await expect(page.locator('#comparison')).toContainText('Upstream unavailable');
 await page.screenshot({path:`.data/screenshots/upstream-comparison-${width}.png`});
});

for(const url of ['javascript:alert(1)','https://user:password@example.org/repo','https://example.org/repo?secret=x','https://example.org/\\evil','https://example.com%2Frepo/path','https://example.org/\u0080','https://example.org/\u202e'])test(`unsafe upstream stays inert: ${url}`,async({page})=>{
 await page.route('**/v1/status',r=>r.fulfill({json:{packages:1}}));
 const p={record_id:'a',package_id:'a',version:'1',name:'A',summary:'A',source_kind:'registry',source:'registry',license:'MIT',details:{},documents:[],evidence:[],provenance:{},upstream:{url,revision:'v1'},ranking_score:null,match_strength:'exact',snippets:[]};
 await page.route('**/v1/search',r=>r.fulfill({json:{snapshot:'test',mode:'lexical',latency_ms:1,results:[p]}}));
 await page.route('**/v1/packages/**',r=>r.fulfill({json:p}));
 await page.goto('/?q=a');
 await expect(page.locator('#detail .upstream')).toHaveText('Upstream unavailable');
 await expect(page.getByRole('link',{name:'Upstream project'})).toHaveCount(0);
 await expect(page.locator('.upstream img')).toHaveCount(0);
});

test('unsafe revision is rejected independently of a valid URL',async({page})=>{
 const p={record_id:'a',package_id:'a',version:'1',name:'A',summary:'A',source_kind:'registry',source:'registry',license:'MIT',details:{},documents:[],evidence:[],provenance:{},upstream:{url:'https://example.org/repo',revision:'v1\u0080'},ranking_score:null,match_strength:'exact',snippets:[]};
 await page.route('**/v1/status',r=>r.fulfill({json:{packages:1}}));
 await page.route('**/v1/search',r=>r.fulfill({json:{snapshot:'test',mode:'lexical',latency_ms:1,results:[p]}}));
 await page.route('**/v1/packages/**',r=>r.fulfill({json:p}));
 await page.goto('/?q=a');
 await expect(page.locator('#detail .upstream')).toHaveText('Upstream unavailable');
 await expect(page.getByRole('link',{name:'Upstream project'})).toHaveCount(0);
});
