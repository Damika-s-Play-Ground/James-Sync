#!/usr/bin/env python3
"""BSC agent draft state machine.
preview: store exact draft or .hold marker. send: guarded public delivery.
Fixes 2026-06-12: HOLD-state persistence + cross-slot dedupe guard.
Fixes 2026-06-14: per-item verification gate + audit log.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, pathlib, re, subprocess, sys
from zoneinfo import ZoneInfo

WS = pathlib.Path(os.environ.get('BSC_WORKSPACE', '/opt/data/james-bsc-live-clean/data/.ocplatform/workspace'))
ROOT = WS / 'state' / 'bsc-agent-drafts'
AUDIT_LOG = ROOT / 'audit.log'
DEV = 'REDACTED_JID'
PUBLIC = 'REDACTED_JID'
ADMINS = {'REDACTED_JID', 'REDACTED_JID', 'REDACTED_JID'}
HOLD_RE = re.compile(r'\b(hold|stop|reject|cancel|do not send|don.t send|wait)\b', re.I)
APPROVE_RE = re.compile(r'^\s*(approve|approved|send|ok|okay|yes)\s*[.!✅👍]*\s*$', re.I)

def now(): return dt.datetime.now(dt.timezone.utc)
def sha(t): return hashlib.sha256(t.encode()).hexdigest()
def draft_path(did): return ROOT / f'{did}.json'
def hold_path(did): return ROOT / f'{did}.hold'
def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    os.replace(tmp, path)
def load(did): return json.loads(draft_path(did).read_text())
def save(d): d['updated_at'] = now().isoformat(); atomic(draft_path(d['draft_id']), d)

def audit(draft_id, action, **fields):
    """Append one structured line to state/bsc-agent-drafts/audit.log."""
    rec = {'ts': now().isoformat(), 'draft_id': draft_id, 'action': action, **fields}
    try:
        ROOT.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    except Exception:
        pass

def items_summary(items):
    """Return (verified, ambiguous, rejected, missing_required_fields_count)."""
    if not isinstance(items, list):
        return (0, 0, 0, 0)
    required = {'bullet_index', 'text', 'source', 'source_excerpt',
                'applies_to_year_groups', 'target_audience_detected',
                'verification_status', 'parent_safe'}
    v = a = r = bad = 0
    for it in items:
        if not isinstance(it, dict) or (required - set(it.keys())):
            bad += 1
            continue
        st = it.get('verification_status')
        if st == 'verified' and it.get('parent_safe') is True:
            v += 1
        elif st == 'ambiguous':
            a += 1
        else:
            r += 1
    return (v, a, r, bad)

def items_dev_notice(items):
    """Return a short DEV-group message listing ambiguous/rejected items.

    Empty string if nothing to report.
    """
    if not isinstance(items, list):
        return ''
    lines = []
    for it in items:
        if not isinstance(it, dict):
            continue
        st = it.get('verification_status')
        if st in (None, 'verified'):
            continue
        snip = (it.get('text') or '')[:140]
        reason = it.get('rejection_reason') or it.get('target_audience_detected') or '?'
        lines.append(f'• [{st}] {snip} — {reason}')
    if not lines:
        return ''
    return 'Withheld items (not sent to parents):\n' + '\n'.join(lines)

def wa_send(jid, text):
    p = subprocess.run(['wacli','send','text','--to',jid,'--message',text],
                       text=True, capture_output=True, timeout=60)
    if p.returncode: raise RuntimeError(p.stderr[-1000:])
    m = re.search(r'\(id\s+([^\)]+)\)', p.stdout)
    return m.group(1) if m else ''

def validate_year3(payload):
    if payload.get('decision') != 'SEND': raise ValueError('decision must be SEND')
    if payload.get('audience') not in ('Year 3','Year 3 parents'):
        raise ValueError('audience must be Year 3 only')
    msg = payload.get('final_message','').strip()
    if not msg: raise ValueError('final_message missing')
    if re.search(r'\b(year\s*4|y4|4b)\b', msg, re.I): raise ValueError('Year 4 content blocked')
    if not payload.get('evidence'): raise ValueError('evidence required')
    if payload.get('risk_flags'): raise ValueError('risk_flags require HOLD')
    return msg

def _word_overlap(a, b):
    wa = set(re.sub(r'[*_`~\W]',' ',a.lower()).split())
    wb = set(re.sub(r'[*_`~\W]',' ',b.lower()).split())
    if not wa or not wb: return 0.0
    return len(wa & wb) / max(len(wa), len(wb))

def check_cross_slot_dedupe(payload, target_date, skip_draft_id=None):
    """Return [(slot, reason)] if this notice was already covered today.
    skip_draft_id: draft_id of the current draft being sent — never compare against itself.
    """
    msg = payload.get('final_message','')
    if not msg or len(msg) < 20: return []
    target = dt.date.fromisoformat(target_date)
    dupes = []
    for slot in ['6am','3pm','weekly','urgent-0700','urgent-1100','urgent-1400',
                 'urgent-1900','urgent-2300','urgent-0300']:
        p = ROOT / f'{target.isoformat()}-{slot}.json'
        if not p.exists(): continue
        # Never compare the draft against itself
        candidate_id = f'{target.isoformat()}-{slot}'
        if skip_draft_id and candidate_id == skip_draft_id: continue
        try:
            prior = json.loads(p.read_text())
            # Only flag if the prior draft was actually SENT (not just PENDING)
            if prior.get('status') not in ('SENT',): continue
            ratio = _word_overlap(msg, prior.get('message',''))
            if ratio > 0.70: dupes.append((slot, f'overlap={ratio:.2f}'))
        except Exception: pass
    if dupes: return dupes
    try:
        p = subprocess.run(['wacli','messages','list','--chat',PUBLIC,
                            '--limit','20','--full','--json'],
                           text=True, capture_output=True, timeout=30, check=False)
        if p.returncode == 0:
            rows = json.loads(p.stdout or '{}').get('data',[])
            if isinstance(rows, dict): rows = rows.get('messages',[])
            for r in rows:
                old = r.get('Text') or r.get('DisplayText') or ''
                ratio = _word_overlap(msg, old)
                if ratio > 0.75:
                    dupes.append(('public-recent', f'overlap={ratio:.2f}'))
                    break
    except Exception: pass
    return dupes

def cmd_preview(a):
    p = json.loads(pathlib.Path(a.input).read_text())
    target = dt.date.fromisoformat(p['target_date'])
    slot = p['slot']
    draft_id = f'{target.isoformat()}-{slot}'
    send_at = dt.datetime.fromisoformat(p['send_at']).astimezone(dt.timezone.utc)
    if send_at <= now(): raise ValueError('send_at must be in future')
    decision = p.get('decision','HOLD')
    if decision == 'HOLD':
        # FIX: persist .hold marker so retries know primary ran and held
        ROOT.mkdir(parents=True, exist_ok=True)
        hold_path(draft_id).write_text(json.dumps({
            'held_at': now().isoformat(),
            'reason': p.get('hold_reason','no reason provided'),
            'slot': slot, 'target_date': target.isoformat()
        }, ensure_ascii=False, indent=2) + '\n')
        wa_send(DEV, f'HOLD — {slot} {target.isoformat()}\n\n{p.get("hold_reason","no new notices")}')
        audit(draft_id, 'PREVIEW_HOLD', reason=p.get('hold_reason'))
        print(f'{draft_id}.hold')
        return
    msg = validate_year3(p)
    items = p.get('items')
    v, am, rj, bad = items_summary(items)
    d = {'draft_id':draft_id,'slot':slot,'target_date':target.isoformat(),
         'status':'PENDING','version':1,'message':msg,'message_sha256':sha(msg),
         'payload':p,'created_at':now().isoformat(),'updated_at':now().isoformat(),
         'send_at':send_at.isoformat(),'preview_message_id':'','history':[]}
    slt = send_at.astimezone(ZoneInfo('Asia/Colombo')).strftime('%-I:%M%p')
    d['preview_message_id'] = wa_send(DEV, f'PREVIEW ONLY — scheduled for {slt}\n\n{msg}')
    d['history'].append({'at':now().isoformat(),'action':'PREVIEW','sha256':d['message_sha256']})
    save(d)
    # Always tell DEV when items metadata is missing or partially unverified.
    if not isinstance(items, list) or len(items) == 0:
        try: wa_send(DEV, f'⚠️ {draft_id}: items[] missing — public send will be BLOCKED by safe-send. Update prompt to emit per-bullet verification metadata.')
        except Exception: pass
    else:
        notice = items_dev_notice(items)
        if notice:
            try: wa_send(DEV, f'{draft_id} — {notice}')
            except Exception: pass
    audit(draft_id, 'PREVIEW', items_total=(len(items) if isinstance(items, list) else 0),
          verified=v, ambiguous=am, rejected=rj, missing_fields=bad, sha=d['message_sha256'])
    print(draft_id)

def cmd_revise(a):
    d = load(a.draft_id)
    if d['status'] not in ('PENDING','APPROVED'): raise ValueError('draft not revisable')
    msg = pathlib.Path(a.message_file).read_text().strip()
    validate_year3({'decision':'SEND','audience':'Year 3','final_message':msg,
                    'evidence':d['payload']['evidence'],'risk_flags':[]})
    d['version'] += 1; d['message'] = msg; d['message_sha256'] = sha(msg); d['status'] = 'PENDING'
    d['history'].append({'at':now().isoformat(),'action':'REVISE',
                         'version':d['version'],'sha256':d['message_sha256'],'by':a.by})
    wa_send(DEV, f"REVISED PREVIEW v{d['version']}\n\n{msg}"); save(d)
    audit(a.draft_id, 'REVISE', version=d['version'], by=a.by, sha=d['message_sha256'])

def cmd_hold(a):
    d = load(a.draft_id)
    d['status'] = 'HOLD'
    d['history'].append({'at':now().isoformat(),'action':'HOLD','reason':a.reason})
    save(d)
    audit(a.draft_id, 'HOLD', reason=a.reason)

def dev_replies(d):
    p = subprocess.run(['wacli','messages','list','--chat',DEV,
                        '--limit','100','--full','--json'],
                       text=True, capture_output=True, timeout=45)
    if p.returncode: raise RuntimeError('cannot inspect dev replies')
    obj = json.loads(p.stdout)
    rows = (obj.get('data') or {}).get('messages', obj.get('data') or [])
    since = dt.datetime.fromisoformat(d['created_at'])
    return [r for r in rows
            if not r.get('FromMe') and r.get('SenderJID') in ADMINS
            and dt.datetime.fromisoformat(r['Timestamp'].replace('Z','+00:00')) >= since]

def cmd_send(a):
    d = load(a.draft_id)
    if d['status'] == 'HOLD': print('HOLD'); return
    if d['status'] == 'SENT': print('SENT'); return
    if now() < dt.datetime.fromisoformat(d['send_at']) and not a.force:
        raise ValueError('send window has not reached send_at')
    # SAFETY: --force in testing must set BSC_SAFE_SEND=1 env var to allow public send.
    # Without it, --force routes to DEV only (not PUBLIC). Prevents accidental public sends during tests.
    if a.force and not os.environ.get('BSC_SAFE_SEND'):
        wa_send(DEV, f'[TEST/FORCE dry-run] {d["draft_id"]}\nMessage:\n{d["message"]}\n\nNOT sent to public group. Set BSC_SAFE_SEND=1 to allow public send with --force.')
        audit(a.draft_id, 'FORCE_DEV_ONLY')
        print('FORCE_DEV_ONLY'); return

    # FIX 2026-06-14: per-item verification pre-check. Block here so we surface
    # a clear DEV notice before invoking safe-send (which would also block).
    items = (d.get('payload') or {}).get('items')
    v, am, rj, bad = items_summary(items)
    if not isinstance(items, list) or len(items) == 0:
        d['status'] = 'HOLD'
        d['history'].append({'at':now().isoformat(),'action':'AUTO_HOLD',
                             'reason':'items[] missing — verification gate'})
        save(d)
        try: wa_send(DEV, f'AUTO-HOLD (verification gate) — {d["draft_id"]}\nitems[] missing; update preview prompt to emit per-bullet verification metadata before public send.')
        except Exception: pass
        audit(a.draft_id, 'AUTO_HOLD', reason='items_missing')
        print('HOLD'); return
    if am or rj or bad:
        d['status'] = 'HOLD'
        d['history'].append({'at':now().isoformat(),'action':'AUTO_HOLD',
                             'reason':f'verification gate: ambiguous={am} rejected={rj} bad_fields={bad}'})
        save(d)
        try:
            notice = items_dev_notice(items)
            wa_send(DEV, f'AUTO-HOLD (verification gate) — {d["draft_id"]}\nverified={v} ambiguous={am} rejected={rj}\n\n{notice}')
        except Exception: pass
        audit(a.draft_id, 'AUTO_HOLD', reason='items_unverified',
              verified=v, ambiguous=am, rejected=rj, bad_fields=bad)
        print('HOLD'); return

    # FIX: cross-slot dedupe guard
    dupes = check_cross_slot_dedupe(d['payload'], d['target_date'], skip_draft_id=d['draft_id'])
    if dupes:
        reason = '; '.join(f'{s}:{r}' for s,r in dupes)
        d['status'] = 'HOLD'
        d['history'].append({'at':now().isoformat(),'action':'AUTO_HOLD',
                             'reason':f'cross-slot-dedupe: {reason}'})
        save(d)
        try: wa_send(DEV, f'AUTO-HOLD (dedupe) — {d["draft_id"]}\nAlready covered: {reason}\nNo public send.')
        except Exception: pass
        audit(a.draft_id, 'AUTO_HOLD', reason='cross_slot_dedupe', dupes=reason)
        print('HOLD'); return
    replies = dev_replies(d)
    texts = [(r.get('Text') or r.get('DisplayText') or '').strip() for r in replies]
    if any(HOLD_RE.search(t) for t in texts):
        d['status'] = 'HOLD'
        d['history'].append({'at':now().isoformat(),'action':'AUTO_HOLD','reason':'admin hold'})
        save(d)
        audit(a.draft_id, 'AUTO_HOLD', reason='admin_hold')
        print('HOLD'); return
    uncertain = [t for t in texts if t and not APPROVE_RE.match(t)]
    if uncertain:
        d['status'] = 'HOLD'
        d['history'].append({'at':now().isoformat(),'action':'AUTO_HOLD','reason':'admin discussion pending'})
        save(d)
        audit(a.draft_id, 'AUTO_HOLD', reason='admin_discussion_pending')
        print('HOLD'); return
    inp = ROOT / f'.{d["draft_id"]}.send.json'
    payload = dict(d['payload']); payload['final_message'] = d['message']; payload['target_group'] = PUBLIC
    atomic(inp, payload)
    try:
        p = subprocess.run([sys.executable, str(WS/'scripts'/'bsc-agent-safe-send.py'),
                            '--input', str(inp), '--send'],
                           text=True, capture_output=True, timeout=90)
    finally: inp.unlink(missing_ok=True)
    if p.returncode:
        err = (p.stderr or p.stdout)[-1200:]
        audit(a.draft_id, 'SEND_BLOCKED', stderr=err[-400:])
        raise RuntimeError(err)
    d['status'] = 'SENT'; d['sent_at'] = now().isoformat()
    d['history'].append({'at':d['sent_at'],'action':'SEND','sha256':d['message_sha256']})
    save(d)
    audit(a.draft_id, 'SENT', sha=d['message_sha256'],
          items_total=len(items), verified=v)
    print('SENT')

def main():
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(required=True)
    x = sp.add_parser('preview'); x.add_argument('--input',required=True); x.set_defaults(fn=cmd_preview)
    x = sp.add_parser('revise'); x.add_argument('draft_id')
    x.add_argument('--message-file',required=True); x.add_argument('--by',default='admin'); x.set_defaults(fn=cmd_revise)
    x = sp.add_parser('hold'); x.add_argument('draft_id')
    x.add_argument('--reason',default='admin hold'); x.set_defaults(fn=cmd_hold)
    x = sp.add_parser('send'); x.add_argument('draft_id')
    x.add_argument('--force',action='store_true'); x.set_defaults(fn=cmd_send)
    x = sp.add_parser('show'); x.add_argument('draft_id')
    x.set_defaults(fn=lambda a: print(json.dumps(load(a.draft_id),ensure_ascii=False,indent=2)))
    a = ap.parse_args(); a.fn(a)

if __name__ == '__main__':
    main()
