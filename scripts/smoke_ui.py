"""Exercise the actual coaching UI against a running local server."""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]

if __name__=='__main__':
    artifacts=ROOT/'artifacts';artifacts.mkdir(exist_ok=True)
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:8000',wait_until='networkidle')
        page.locator('#use-plan').wait_for()
        assert page.locator('.recommend-card .formation-number').inner_text()
        page.select_option('#opponent','3-5-2')
        page.select_option('#objective','protect_lead')
        page.click('#recommend-button');page.wait_for_timeout(500)
        assert '3-5-2' in page.locator('#opponent-details').inner_text()
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path=str(artifacts/'planner-desktop.png'),full_page=True)
        page.click('#use-plan');page.click('#demo-button')
        page.wait_for_function("document.getElementById('point-count').textContent.includes('4 of 4')")
        page.locator('#analyse-button').click()
        page.locator('#review-workspace').wait_for(state='visible',timeout=120000)
        assert '100%' in page.locator('#summary-stats').inner_text()
        page.locator('[data-review-open]').first.click()
        event_id=page.locator('[data-review-id]').first.get_attribute('data-review-id')
        page.select_option(f'#verdict-{event_id}','confirmed')
        page.fill(f'#notes-{event_id}','Cover the channel before the defender steps out.')
        page.fill(f'#reviewer-{event_id}','UI smoke reviewer')
        page.locator(f'#review-form-{event_id} button[type=submit]').click()
        page.wait_for_function("document.querySelector('.event-card .pill').textContent==='confirmed'")
        # Independent review tools must accept missed issues and reviewed
        # negative periods without copying automatic candidates into truth.
        page.fill('#label-reviewer','Automated UI fixture, not a human coach')
        page.select_option('#label-role','analyst')
        page.fill('#manual-start','1');page.fill('#manual-end','1.5')
        page.select_option('#manual-kind','unit_gap')
        page.fill('#manual-notes','Automated UI fixture — not tactical ground truth')
        page.locator('#manual-event-form button[type=submit]').click()
        page.locator('#reviewed-period-form button[type=submit]').click()
        page.check('#labels-attested');page.click('#save-human-review')
        page.wait_for_function("document.getElementById('human-review-status').textContent.includes('Saved revision 1')")
        href=page.locator('#export-human-labels').get_attribute('href')
        exported=page.request.get('http://127.0.0.1:8000'+href).json()
        assert not exported['events_reviewed']
        assert [e['kind'] for e in exported['events']]==['unit_gap']
        assert exported['reviewed_intervals']==[[0,6]]
        page.locator('[data-jump]').first.click();page.wait_for_timeout(400)
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path=str(artifacts/'review-desktop.png'),full_page=True)
        page.click('#next-frame');page.click('#play-review');page.wait_for_timeout(600);page.click('#play-review')
        page.click('[data-view=sessions]');page.locator('[data-open-job]').first.wait_for()
        page.locator('[data-open-job]').first.click();page.locator('#review-workspace').wait_for(state='visible')
        assert 'confirmed' in page.locator('.event-card .pill').first.inner_text()
        page.wait_for_function("document.getElementById('human-review-status').textContent.includes('Saved revision 1')")
        assert 'Automated UI fixture' in page.locator('#manual-events').inner_text()
        page.click('[data-view=planner]');page.set_viewport_size({'width':390,'height':844})
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path=str(artifacts/'planner-mobile.png'),full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'), 'Mobile layout overflows'
        page.click('#help-top');assert page.locator('#help-dialog').is_visible()
        page.locator('#help-dialog .primary').click()
        page.click('[data-view=analysis]')
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path=str(artifacts/'review-mobile.png'),full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'), 'Mobile analysis overflows'
        # Exercise a real native file upload and keyboard calibration, not just
        # the built-in demonstration path.
        clip=ROOT/'gettyimages-1293195390-640_adpp.mp4'
        if clip.exists():
            page.set_viewport_size({'width':1440,'height':1000})
            page.locator('#video-file').set_input_files(str(clip))
            page.wait_for_function("document.getElementById('upload-info').textContent.includes('gettyimages')")
            page.locator('#calibration-canvas').wait_for(state='visible')
            page.locator('#calibration-panel summary').filter(has_text='Precise landmark coordinates').click()
            page.fill('#points-json','[[111,47],[651,47],[765,425],[5,425]]')
            page.click('#apply-points')
            page.wait_for_function("document.getElementById('point-count').textContent.includes('4 of 4')")
            page.click('#save-keyframe')
            assert page.locator('.keyframe-chip').count()==1
            page.evaluate('window.scrollTo(0,0)')
            page.screenshot(path=str(artifacts/'real-upload-calibration.png'),full_page=True)
        assert not errors,errors
        browser.close()
    report={'status':'passed','checks':['formation inputs','context-dependent advice','demo analysis','pitch review','event notes persisted','missed-event annotations','reviewed negative periods','human labels separate from predictions','analyst labels do not claim coach verification','playback','session reopening','mobile layout','help','native real-video upload and keyboard calibration when supplied clip exists'],'browser_errors':errors}
    (artifacts/'ui-smoke.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
