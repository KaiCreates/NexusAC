"""Disconnects page: reason classification and the summary views.

    python tests/disconnectcheck.py

Runs without a database or Supabase: db.query is replaced with rows shaped
exactly like nx_events.
"""
import os, sys, types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# app.security needs live config to import; the summary only wants now().
fake_security = types.ModuleType('app.security')
NOW = 1_800_000_000
fake_security.now = lambda: NOW
sys.modules['app.security'] = fake_security
fake_db = types.ModuleType('app.db')
sys.modules['app.db'] = fake_db
import app  # noqa: E402
app.db = fake_db
from app import disconnects as dc  # noqa: E402

passed, failed = [], []
def check(name, got, want):
    ok = got == want
    (passed if ok else failed).append(name)
    print(('  PASS  ' if ok else '  FAIL  ') + name + ('' if ok else '  -> got %r want %r' % (got, want)))

print('== classification ==')
cases = [
    ('Exiting', 'quit'),
    ('Disconnected.', 'quit'),
    ('Quit.', 'quit'),
    ('Game crashed: GTA5_b3258.exe!sub_1411D95F4 (0x3b)', 'crash'),
    ('Game crashed: gta-core-five.dll+4C3F2', 'crash'),
    ('Unhandled exception: ERR_GFX_D3D_INIT', 'crash'),
    ('Server->client connection timed out. Pending commands: 12.\nCommand list:\n', 'timeout'),
    ('Timed out after 60 seconds (1, 0)', 'timeout'),
    ('Reliable network event overflow.', 'network'),
    ('[txAdmin] You have been kicked from this server.\nReason: afk', 'kick'),
    ('Server shutting down: Scheduled restart', 'server'),
    ('Failed to download resource: kaizombie', 'resource'),
    ('You are banned from this server. Ban ID: NX-B-7Q2', 'ban'),
    ('something nobody has seen before', 'other'),
]
for reason, want in cases:
    check('%-58r -> %s' % (reason[:58], want), dc.classify(reason)['category'], want)

check('NexusAC kick is attributed to NexusAC, whatever the text says',
      (dc.classify('Exiting', {'by': 'nexus', 'action': 'kick'})['category'],
       dc.classify('Exiting', {'by': 'nexus', 'action': 'kick'})['by']), ('kick', 'nexus'))
check('NexusAC ban', dc.classify('x', {'by': 'nexus', 'action': 'ban'})['category'], 'ban')
check('txAdmin kick is attributed to txAdmin', dc.classify('[txAdmin] kicked: afk')['by'], 'txadmin')
check('crash signature keeps where it crashed',
      dc.classify('Game crashed: GTA5_b3258.exe+1026D45  (more text)')['signature'], 'GTA5_b3258.exe+1026D45')

print('== summary ==')
def row(i, at, name, reason, **data):
    return {'id': i, 'at': at, 'sender': 'license:' + name, 'sender_name': name,
            'data': {'reason': reason, **data}}
rows = [
    # A crash attack: four players crash within 10 s, standing near each other.
    row(1, NOW - 600, 'A', 'Game crashed: GTA5_b3258.exe+1026D45', x=100, y=100),
    row(2, NOW - 597, 'B', 'Game crashed: GTA5_b3258.exe+1026D45', x=130, y=90),
    row(3, NOW - 594, 'C', 'Game crashed: GTA5_b3258.exe+1026D45', x=110, y=140),
    row(4, NOW - 591, 'D', 'Server->client connection timed out.', x=90, y=120),
    # A server restart: everyone leaves at once, and that is not an attack.
    row(5, NOW - 3000, 'E', 'Server shutting down: restart'),
    row(6, NOW - 2999, 'F', 'Server shutting down: restart'),
    row(7, NOW - 2998, 'G', 'Server shutting down: restart'),
    # One player who keeps crashing on their own.
    row(8, NOW - 9000, 'H', 'Game crashed: nvwgf2umx.dll+12AB'),
    row(9, NOW - 8000, 'H', 'Game crashed: nvwgf2umx.dll+12AB'),
    row(10, NOW - 7000, 'H', 'Game crashed: nvwgf2umx.dll+12AB'),
    row(11, NOW - 100, 'I', 'Exiting', sessionSec=3600, by='nexus', action='kick', nexusReason='crash payload'),
]
fake_db.query = lambda sql, params: sorted(rows, key=lambda r: -r['at'])
s = dc.summary('ws', 'srv', '24h')

check('totals: 6 crashes', s['totals']['crash'], 6)
check('totals: 1 timeout', s['totals']['timeout'], 1)
check('totals: 3 server stop', s['totals']['server'], 3)
check('totals: NexusAC kick counted as a kick', s['totals']['kick'], 1)
verdicts = {c['verdict'] for c in s['clusters']}
check('four crashes close together in 10 s: possible crash attack', 'possible crash attack' in verdicts, True)
check('everyone leaving at a restart is a server restart, not an attack', 'server restart' in verdicts, True)
top = s['signatures'][0]
check('the attack signature ranks first (3 different players)', (top['signature'], top['playerCount']),
      ('GTA5_b3258.exe+1026D45', 3))
check('one player crashing alone three times: keeps crashing', [p['name'] for p in s['repeaters']], ['H'])
check('rows carry the category for the page', s['rows'][0]['category'], 'kick')

print('%d passed, %d failed' % (len(passed), len(failed)))
sys.exit(1 if failed else 0)
