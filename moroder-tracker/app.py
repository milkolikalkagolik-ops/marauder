import sqlite3, datetime, secrets, json, os, time, requests, threading, csv, io
from flask import Flask, request, redirect, render_template_string, session, send_from_directory, jsonify, Response, flash
from werkzeug.security import generate_password_hash, check_password_hash
import psutil
import urllib.request, json as json_lib
import base64
import socket
import traceback
import hashlib
import functools

cache_store = {}
def turbo_cache(timeout=60):
    def decorator(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            now = time.time()
            # Ключ зависит только от URL и параметров запроса (например, страница)
            key = request.path + "?" + request.query_string.decode()
            cached = cache_store.get(key)
            if cached and (now - cached['time']) < timeout:
                return cached['response']
            response = f(*args, **kwargs)
            cache_store[key] = {'response': response, 'time': now}
            return response
        return wrapped
    return decorator

def get_date_range(period, start_str, end_str):
    now = datetime.datetime.now()
    if period == 'today':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif period == 'yesterday':
        yesterday = now - datetime.timedelta(days=1)
        start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif period == '3days':
        start = now - datetime.timedelta(days=3)
        end = now
    elif period == 'week':
        start = now - datetime.timedelta(weeks=1)
        end = now
    elif period == '2weeks':
        start = now - datetime.timedelta(weeks=2)
        end = now
    elif period == 'month':
        start = now - datetime.timedelta(days=30)
        end = now
    elif period == 'year':
        start = now - datetime.timedelta(days=365)
        end = now
    elif period == 'all':
        return None, None
    elif period == 'custom' and start_str and end_str:
        try:
            start = datetime.datetime.strptime(start_str, '%Y-%m-%d')
            end = datetime.datetime.strptime(end_str, '%Y-%m-%d') + datetime.timedelta(days=1) - datetime.timedelta(seconds=1)
            return start, end
        except:
            return None, None
    else:
        return None, None  # по умолчанию всё время
    return start, end

def render_partial(template, **context):
    """Рендерит шаблон и вырезает только контент между метками MAIN CONTENT."""
    full = render_template_string(template, **context)
    start_marker = '<!-- BEGIN MAIN CONTENT -->'
    end_marker = '<!-- END MAIN CONTENT -->'
    start = full.find(start_marker)
    end = full.find(end_marker)
    if start != -1 and end != -1:
        # возвращаем содержимое между маркерами, включая конечный маркер
        return full[start + len(start_marker):end + len(end_marker)]
    return full  # на случай, если маркеры не найдены
# ------------------------------------------------------------
# ГЛОБАЛЬНЫЕ НАСТРОЙКИ И ЗАГРУЗКА РЕСУРСОВ
# ------------------------------------------------------------
def get_country_by_ip(ip):
    try:
        url = f'http://ip-api.com/json/{ip}?fields=countryCode,city'
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = json_lib.loads(resp.read().decode())
            return {'country': data.get('countryCode', ''), 'city': data.get('city', '')}
    except:
        return {'country': '', 'city': ''}

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = False   # чтобы Jinja2 не пересматривал файлы
app.jinja_env.cache = {}                      # кэш скомпилированных шаблонов
app.jinja_env.filters['fromjson'] = json_lib.loads
LOGO_PATH = '/opt/moroder-tracker/jack.png'
FAVICON_PATH = '/opt/moroder-tracker/jack.png'

try:
    with open(LOGO_PATH, 'rb') as f:
        LOGO_BASE64 = base64.b64encode(f.read()).decode('utf-8')
except Exception:
    LOGO_BASE64 = ''
try:
    with open(FAVICON_PATH, 'rb') as f:
        FAVICON_BASE64 = base64.b64encode(f.read()).decode('utf-8')
except Exception:
    FAVICON_BASE64 = ''

app.secret_key = 'morader_secret_key_change_me_v2'
DB = 'tracker.db'
PER_PAGE = 30
TEMPLATES_FILE = 'affiliate_networks.json'
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'landers')
# Загружаем список стран из файла (или создаём полный словарь)
COUNTRY_CODES = {}
try:
    with open('counters.json', 'r', encoding='utf-8') as f:
        data = json_lib.load(f)
        if isinstance(data, dict):
            COUNTRY_CODES = data
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and 'code' in item and 'name' in item:
                    COUNTRY_CODES[item['code']] = item['name']
except:
    # Если файла нет, подставляем полный словарь (альтернатива)
    COUNTRY_CODES = {
        # Твой текущий список + ещё 200+ стран
        'KZ': 'Казахстан',
        'LT': 'Литва',
        # ... (можешь скопировать полный список отсюда: https://github.com/annexare/Countries/blob/main/countries.json)
    }
DOMAIN = 'localhost'

# Загружаем справочник стран один раз при старте
COUNTRY_CODES = {}
try:
    with open('/opt/moroder-tracker/counters.json', 'r', encoding='utf-8') as f:
        data = json_lib.load(f)
        for c in data.get('countries', []):
            COUNTRY_CODES[c['code']] = c['name']
except Exception as e:
    print(f"COUNTRY LOAD ERROR: {e}", flush=True)

# Палитра для тегов (10 цветов)
AVAILABLE_TAGS = ['dating', '30+', 'soi', 'nutra', 'gambling', 'finance', 'push', 'fb', 'tier1', 'tier2']
TAG_COLOR_MAP = {
    'dating': '#e74c3c',
    '30+': '#e67e22',
    'soi': '#f1c40f',
    'nutra': '#2ecc71',
    'gambling': '#3498db',
    'finance': '#9b59b6',
    'push': '#1abc9c',
    'fb': '#e84393',
    'tier1': '#f39c12',
    'tier2': '#00b894'
}

TAG_COLORS = [
    '#e74c3c', '#3498db', '#2ecc71', '#f1c40f', '#9b59b6',
    '#1abc9c', '#e67e22', '#ecf0f1', '#95a5a6', '#34495e'
]

# ------------------------------------------------------------
# БАЗА ДАННЫХ
# ------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    # Пользователи, группы, лендинги
    c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password_hash TEXT, role TEXT DEFAULT 'guest')''')
   # c.execute("INSERT OR IGNORE INTO users (username, password_hash, role) VALUES ('admin', ?, 'admin')", (generate_password_hash('admin'),))
    c.execute('''CREATE TABLE IF NOT EXISTS groups (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)''')

    c.execute('''CREATE TABLE IF NOT EXISTS landers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, group_id INTEGER, url TEXT DEFAULT '', language TEXT DEFAULT '', type TEXT DEFAULT 'url', file_path TEXT DEFAULT '', index_file TEXT DEFAULT 'index.html', created_at DATETIME DEFAULT CURRENT_TIMESTAMP, is_archived INTEGER DEFAULT 0, tags TEXT DEFAULT '')''')

    # Офферы, источники, партнёрки
    c.execute('''CREATE TABLE IF NOT EXISTS offers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, group_id INTEGER, affiliate_network_id INTEGER, url TEXT DEFAULT '', payout REAL DEFAULT 0, country TEXT DEFAULT '', cap_enabled INTEGER DEFAULT 0, cap_clicks INTEGER DEFAULT 0, cap_conversions INTEGER DEFAULT 0, cap_reset_period_hours INTEGER DEFAULT 0, cap_reset_time_utc3 TEXT DEFAULT '', reserve_offer_id INTEGER DEFAULT NULL, default_lander_id INTEGER DEFAULT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, is_archived INTEGER DEFAULT 0, tags TEXT DEFAULT '')''')

    c.execute('''CREATE TABLE IF NOT EXISTS traffic_sources (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, type TEXT DEFAULT 'postback', url_template TEXT DEFAULT '', postback_url_template TEXT DEFAULT '', api_key TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS affiliate_networks (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, url_template TEXT DEFAULT '', postback_url_template TEXT DEFAULT '')''')
    # Кампании (с поддержкой JSON-массива стран)
    c.execute('''CREATE TABLE IF NOT EXISTS campaigns (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, lander_id INTEGER, offer_id INTEGER, cpc REAL DEFAULT 0.002, traffic_source_id INTEGER, affiliate_network_id INTEGER, domain_id INTEGER DEFAULT NULL, api_spent REAL DEFAULT 0, js_challenge_enabled INTEGER DEFAULT 0, js_challenge_level TEXT DEFAULT 'easy', created_at DATETIME DEFAULT CURRENT_TIMESTAMP, is_archived INTEGER DEFAULT 0, tags TEXT DEFAULT '', countries TEXT DEFAULT '[]')''')
    c.execute('''CREATE TABLE IF NOT EXISTS campaign_stats (
        campaign_id INTEGER PRIMARY KEY,
        clicks INTEGER DEFAULT 0,
        leads INTEGER DEFAULT 0,
        approved INTEGER DEFAULT 0,
        revenue REAL DEFAULT 0,
        cost REAL DEFAULT 0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS clicks (id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id INTEGER, lander_id INTEGER, offer_id INTEGER, click_id TEXT, ip TEXT, user_agent TEXT, country TEXT, city TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS leads (id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id INTEGER, offer_id INTEGER, lander_id INTEGER, click_id TEXT, status TEXT DEFAULT 'pending', payout REAL DEFAULT 0, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS conversions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        click_id TEXT,
        payout REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS rules (id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id INTEGER NOT NULL, name TEXT, condition_type TEXT, operator TEXT, value TEXT, action TEXT, lander_id INTEGER, offer_id INTEGER, js_challenge INTEGER DEFAULT 0, priority INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS postback_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    click_id TEXT,
    payout REAL,
    status TEXT DEFAULT 'received',
    raw_url TEXT,
    ip TEXT,
    campaign_id INTEGER,
    offer_id INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS domains (id INTEGER PRIMARY KEY AUTOINCREMENT, domain TEXT UNIQUE NOT NULL, is_default INTEGER DEFAULT 0, ssl_status TEXT DEFAULT 'unknown', added_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS traffic_costs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        traffic_source_id INTEGER NOT NULL,
        campaign_id INTEGER DEFAULT NULL,
        date TEXT NOT NULL,
        cost REAL DEFAULT 0,
        impressions INTEGER DEFAULT 0,
        clicks INTEGER DEFAULT 0,
        source_type TEXT DEFAULT 'manual',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS license (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        key TEXT DEFAULT '',
        activated INTEGER DEFAULT 0
    )''')
    c.execute("INSERT OR IGNORE INTO license (id, key, activated) VALUES (1, '', 0)")

    # Миграция старых колонок (без ошибок)
    def add_col(table, col, def_val):
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {def_val}")
        except sqlite3.OperationalError:
            pass
    add_col('campaigns', 'is_archived', 'INTEGER DEFAULT 0')
    add_col('campaigns', 'tags', "TEXT DEFAULT ''")
    add_col('campaigns', 'countries', "TEXT DEFAULT '[]'")
    add_col('campaigns', 'group_id', 'INTEGER DEFAULT NULL')
    add_col('landers', 'is_archived', 'INTEGER DEFAULT 0')
    add_col('landers', 'tags', "TEXT DEFAULT ''")
    add_col('clicks', 'external_click_id', "TEXT DEFAULT ''")
    add_col('campaigns', 's2s_postback_url', "TEXT DEFAULT ''")
    add_col('postback_log', 'raw_params', "TEXT DEFAULT ''")
    add_col('traffic_sources', 'url_template', "TEXT DEFAULT ''")
    add_col('offers', 'is_archived', 'INTEGER DEFAULT 0')
    add_col('offers', 'tags', "TEXT DEFAULT ''")
    add_col('traffic_sources', 's2s_postback_url', "TEXT DEFAULT ''")
    add_col('users', 'api_key', "TEXT DEFAULT ''")
    add_col('leads', 's2s_sent', 'INTEGER DEFAULT 0')
    add_col('traffic_costs', 'click_id', "TEXT DEFAULT ''")
    add_col('campaigns', 'params_mapping', "TEXT DEFAULT '{}'")
    add_col('campaigns', 'ip_blacklist', "TEXT DEFAULT ''")
    add_col('campaigns', 'ip_whitelist', "TEXT DEFAULT ''")
    # Сабы и цель
    sub_params = []
    for i in range(1, 12):
        add_col('clicks', f'sub{i}', "TEXT DEFAULT ''")
    add_col('leads', 'goal', "TEXT DEFAULT 'default'")

    # Перенос старого домена из settings
    try:
        c.execute("SELECT value FROM settings WHERE key='domain'")
        old_domain = c.fetchone()
        c.execute("SELECT COUNT(*) FROM domains")
        if old_domain and old_domain[0] and c.fetchone()[0] == 0:
            c.execute("INSERT INTO domains (domain, is_default) VALUES (?, 1)", (old_domain[0],))
    except:
        pass

    # Корзина
    add_col('campaigns', 'in_trash', 'INTEGER DEFAULT 0')
    add_col('campaigns', 'trashed_at', 'DATETIME')
    add_col('landers', 'in_trash', 'INTEGER DEFAULT 0')
    add_col('landers', 'trashed_at', 'DATETIME')
    add_col('offers', 'in_trash', 'INTEGER DEFAULT 0')
    add_col('offers', 'trashed_at', 'DATETIME')

    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_click_id ON leads(click_id)")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_traffic_costs_click ON traffic_costs(click_id, traffic_source_id)")

    conn.commit()
    conn.close()

def load_domain():
    global DOMAIN
    try:
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("SELECT domain FROM domains WHERE is_default=1 LIMIT 1")
        row = c.fetchone()
        if row and row[0]:
            DOMAIN = row[0]
        else:
            c.execute("SELECT domain FROM domains LIMIT 1")
            any_row = c.fetchone()
            if any_row:
                DOMAIN = any_row[0]
        conn.close()
    except:
        pass

init_db()
load_domain()

# Фоновая синхронизация Push.House
def sync_api_spent():
    while True:
        time.sleep(3600)
        try:
            conn = sqlite3.connect(DB)
            c = conn.cursor()
            
            # Синхронизация Push.House
            c.execute("SELECT id, name, api_key FROM traffic_sources WHERE api_key != ''")
            for src_id, src_name, api_key in c.fetchall():
                try:
                    resp = requests.get('https://api.push.house/v1/statistics',
                                        headers={'Authorization': f'Bearer {api_key}'},
                                        params={'date_from': (datetime.datetime.now() - datetime.timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S'),
                                                'date_to': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
                    if resp.status_code == 200:
                        for item in resp.json().get('campaigns', []):
                            c.execute("UPDATE campaigns SET api_spent = api_spent + ? WHERE name=? AND traffic_source_id=?",
                                      (item.get('spent', 0), item.get('name'), src_id))
                except:
                    pass

            # Очистка корзины
            try:
                c.execute("SELECT value FROM settings WHERE key='trash_days'")
                row = c.fetchone()
                days = int(row[0]) if row and row[0].isdigit() else 7
                if days > 0:
                    cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
                    # Кампании
                    c.execute("SELECT id FROM campaigns WHERE in_trash=1 AND trashed_at IS NOT NULL AND trashed_at < ?", (cutoff,))
                    for (cid,) in c.fetchall():
                        c.execute("DELETE FROM clicks WHERE campaign_id=?", (cid,))
                        c.execute("DELETE FROM leads WHERE campaign_id=?", (cid,))
                        c.execute("DELETE FROM rules WHERE campaign_id=?", (cid,))
                        c.execute("DELETE FROM campaigns WHERE id=?", (cid,))
                    # Лендинги
                    c.execute("DELETE FROM landers WHERE in_trash=1 AND trashed_at IS NOT NULL AND trashed_at < ?", (cutoff,))
                    # Офферы
                    c.execute("DELETE FROM offers WHERE in_trash=1 AND trashed_at IS NOT NULL AND trashed_at < ?", (cutoff,))
            except:
                pass

            conn.commit()
            conn.close()
        except:
            pass

threading.Thread(target=sync_api_spent, daemon=True).start()

# Функция для обновления кэша статистики кампаний
def refresh_campaign_stats():
    try:
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        # Очищаем старый кэш
        c.execute("DELETE FROM campaign_stats")
        # Пересчитываем статистику по всем активным кампаниям
        c.execute('''
            INSERT INTO campaign_stats (campaign_id, clicks, leads, approved, revenue, cost)
            SELECT 
                c.id,
                (SELECT COUNT(*) FROM clicks WHERE campaign_id = c.id),
                (SELECT COUNT(*) FROM leads WHERE campaign_id = c.id),
                (SELECT COUNT(*) FROM leads WHERE campaign_id = c.id AND status='approved'),
                (SELECT COALESCE(SUM(payout),0) FROM leads WHERE campaign_id = c.id AND status='approved'),
                (SELECT COALESCE(MAX(api_spent), c.cpc * (SELECT COUNT(*) FROM clicks WHERE campaign_id = c.id)) FROM campaigns WHERE id = c.id)
            FROM campaigns c WHERE c.in_trash = 0
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        # Логируем ошибку, чтобы знать, что что-то пошло не так
        print(f"Stats refresh failed: {e}")

# Фоновый поток, который обновляет кэш каждые 60 секунд
def stats_updater():
    while True:
        time.sleep(60)
        try:
            refresh_campaign_stats()
            print("STATS_UPDATER: кэш обновлён")  # временный вывод в консоль
        except Exception as e:
            print(f"STATS_UPDATER ERROR: {e}")

threading.Thread(target=stats_updater, daemon=True).start()

# ------------------------------------------------------------
# АВТОРИЗАЦИЯ
# ------------------------------------------------------------
_cached_ip = None
_cached_ip_time = 0

def get_server_ip():
    global _cached_ip, _cached_ip_time
    # Если IP уже получен в последний час, возвращаем его мгновенно
    if _cached_ip and (time.time() - _cached_ip_time < 3600):
        return _cached_ip
    # Пробуем быстро получить внешний IP (таймаут 2 сек)
    try:
        with urllib.request.urlopen('https://ifconfig.me/ip', timeout=2) as resp:
            _cached_ip = resp.read().decode().strip()
            _cached_ip_time = time.time()
            return _cached_ip
    except:
        pass
    # Если внешний IP не получили, берём локальный
    try:
        _cached_ip = socket.gethostbyname(socket.gethostname())
    except:
        _cached_ip = '127.0.0.1'
    _cached_ip_time = time.time()
    return _cached_ip

def get_user(username):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    return dict(zip(['id','username','password_hash','role'], row)) if row else None

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Инициализация сессии
    if 'failed_attempts' not in session:
        session['failed_attempts'] = 0
        session['blocked_until'] = 0  # timestamp

    if request.method == 'POST':
        # Проверка блокировки
        blocked_until = session.get('blocked_until', 0)
        if blocked_until > time.time():
            remaining = int(blocked_until - time.time())
            return render_template_string(LOGIN_HTML, error=f"Слишком много попыток. Попробуйте через {remaining} сек.", blocked=True)

        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = get_user(username)
        if user and check_password_hash(user['password_hash'], password):
            # Успешный вход – сбрасываем счётчик
            session['failed_attempts'] = 0
            session['blocked_until'] = 0
            session.update(logged_in=True, user_id=user['id'], username=user['username'], role=user['role'])
            return redirect('/dashboard')
        else:
            # Увеличиваем счётчик
            session['failed_attempts'] += 1
            if session['failed_attempts'] >= 3:
                session['blocked_until'] = time.time() + 300  # 5 минут
                session['failed_attempts'] = 0  # сброс, чтобы после блокировки начать заново
                return render_template_string(LOGIN_HTML, error="Превышено количество попыток. Вход заблокирован на 5 минут.", blocked=True)
            else:
                attempts_left = 3 - session['failed_attempts']
                return render_template_string(LOGIN_HTML, error=f"Неверный логин или пароль. Осталось попыток: {attempts_left}", blocked=False)

    # GET запрос – показать форму
    return render_template_string(LOGIN_HTML, error='', blocked=False)

def api_login_required(f):
    def wrap(*args, **kwargs):
        # Сначала проверяем сессию
        if session.get('logged_in'):
            return f(*args, **kwargs)
        # Проверяем API-ключ
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if api_key:
            conn = sqlite3.connect(DB)
            c = conn.cursor()
            c.execute("SELECT id, username, role FROM users WHERE api_key=?", (api_key,))
            user = c.fetchone()
            conn.close()
            if user:
                # Авторизуем временно (без установки сессии)
                request.user_id = user[0]
                request.username = user[1]
                request.role = user[2]
                return f(*args, **kwargs)
        return jsonify({'error': 'Unauthorized'}), 401
    wrap.__name__ = f.__name__
    return wrap

def login_required(f):
    def wrap(*args, **kwargs):
        if not session.get('logged_in'): return redirect('/login')
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

def admin_required(f):
    def wrap(*args, **kwargs):
        if session.get('role') != 'admin': return "Доступ запрещён", 403
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap



@app.route('/')
@login_required
def index():
    return redirect('/dashboard')


# ------------------------------------------------------------
# НАСТРОЙКИ (АДМИН)
# ------------------------------------------------------------
@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings_page():
    global DOMAIN
    if request.method == 'POST':
        if request.method == 'POST' and session.get('role') != 'admin':
            return "Доступ запрещён", 403
        # Сохранение глобальных списков IP
        if 'ip_blacklist' in request.form or 'ip_whitelist' in request.form:
            black = request.form.get('ip_blacklist', '').strip()
            white = request.form.get('ip_whitelist', '').strip()
            conn = sqlite3.connect(DB)
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('global_ip_blacklist', ?)", (black,))
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('global_ip_whitelist', ?)", (white,))
            conn.commit()
            conn.close()
            flash('Глобальные списки IP обновлены', 'success')
            return redirect('/settings')

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, domain, is_default, ssl_status FROM domains ORDER BY is_default DESC, id ASC")
    domains = c.fetchall()
    c.execute('SELECT id, username, role FROM users ORDER BY username')
    users = c.fetchall()

    # Загружаем данные корзины
    trash_days = 7
    c.execute("SELECT value FROM settings WHERE key='trash_days'")
    trash_row = c.fetchone()
    if trash_row and trash_row[0].isdigit():
        trash_days = int(trash_row[0])

    trashed_campaigns = c.execute('''SELECT id, name, type, in_trash, trashed_at FROM
                                     (SELECT id, name, 'campaign' as type, in_trash, trashed_at FROM campaigns WHERE in_trash=1
                                      UNION ALL
                                      SELECT id, name, 'lander' as type, in_trash, trashed_at FROM landers WHERE in_trash=1
                                      UNION ALL
                                      SELECT id, name, 'offer' as type, in_trash, trashed_at FROM offers WHERE in_trash=1)
                                     ORDER BY trashed_at DESC''').fetchall()

    # Глобальные списки IP (читаем до закрытия соединения)
    c.execute("SELECT value FROM settings WHERE key='global_ip_blacklist'")
    row = c.fetchone()
    global_ip_blacklist = row[0] if row else ''
    c.execute("SELECT value FROM settings WHERE key='global_ip_whitelist'")
    row = c.fetchone()
    global_ip_whitelist = row[0] if row else ''
    c.execute('SELECT id, username, role, api_key FROM users ORDER BY username')
    users = c.fetchall()
    
    conn.close()

    doc_content = ''
    doc_path = '/opt/moroder-tracker/doc.txt'
    if os.path.exists(doc_path):
        with open(doc_path, 'r') as f:
            doc_content = f.read()

    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    load = psutil.getloadavg()
    uptime = time.time() - psutil.boot_time()
    uptime_str = str(datetime.timedelta(seconds=int(uptime)))
    local_ip = socket.gethostbyname(socket.gethostname())
    if request.headers.get('HX-Request'):
        return render_partial(SETTINGS_HTML,
                                  domains=domains,
                                  users=users,
                                  cpu=cpu,
                                  mem=mem,
                                  disk=disk,
                                  load=load,
                                  uptime_str=uptime_str,
                                  local_ip=local_ip,
                                  active_page='settings',
                                  doc_content=doc_content,
                                  trashed_items=trashed_campaigns,
                                  trash_days=trash_days,
                                  global_ip_blacklist=global_ip_blacklist,
                                  global_ip_whitelist=global_ip_whitelist)

    return render_template_string(SETTINGS_HTML,
                                  domains=domains,
                                  users=users,
                                  cpu=cpu,
                                  mem=mem,
                                  disk=disk,
                                  load=load,
                                  uptime_str=uptime_str,
                                  local_ip=local_ip,
                                  active_page='settings',
                                  doc_content=doc_content,
                                  trashed_items=trashed_campaigns,
                                  trash_days=trash_days,
                                  global_ip_blacklist=global_ip_blacklist,
                                  global_ip_whitelist=global_ip_whitelist)
# ------ Управление доменами ------
@app.route('/domain/add', methods=['POST'])
@login_required
@admin_required
def add_domain():
    domain = request.form.get('domain','').strip()
    if domain:
        conn = sqlite3.connect(DB)
        try:
            conn.execute("INSERT INTO domains (domain) VALUES (?)", (domain,))
            conn.commit()
        except: pass
        conn.close()
    return redirect('/settings')

@app.route('/domain/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_domain(id):
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM domains WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect('/settings')

@app.route('/domain/set_default/<int:id>', methods=['POST'])
@login_required
@admin_required
def set_default_domain(id):
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE domains SET is_default=0")
    conn.execute("UPDATE domains SET is_default=1 WHERE id=?", (id,))
    conn.commit()
    conn.close()
    global DOMAIN
    load_domain()
    return redirect('/settings')

# ------ Пользователи (админ) ------
@app.route('/admin/users')
@admin_required
def admin_users():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT id, username, role FROM users ORDER BY username')
    users = c.fetchall()
    conn.close()
    if request.headers.get('HX-Request'):
        return render_partial(USERS_HTML, users=users, active_page='admin')
    return render_template_string(USERS_HTML, users=users, active_page='admin')

@app.route('/admin/user/create', methods=['POST'])
@admin_required
def create_user():
    username = request.form['username'].strip()
    password = request.form['password'].strip()
    role = request.form.get('role', 'guest')
    conn = sqlite3.connect(DB)
    try:
        conn.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                     (username, generate_password_hash(password), role))
        conn.commit()
    except: pass
    conn.close()
    return redirect('/admin/users')

@app.route('/admin/user/edit/<int:id>', methods=['POST'])
@admin_required
def edit_user(id):
    username = request.form['username'].strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'guest')
    conn = sqlite3.connect(DB)
    if password:
        conn.execute("UPDATE users SET username=?, password_hash=?, role=? WHERE id=?",
                     (username, generate_password_hash(password), role, id))
    else:
        conn.execute("UPDATE users SET username=?, role=? WHERE id=?", (username, role, id))
    conn.commit()
    conn.close()
    return redirect('/admin/users')

@app.route('/admin/user/delete/<int:id>', methods=['POST'])
@admin_required
def delete_user(id):
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM users WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect('/admin/users')

# ------ Состояние сервера ------
@app.route('/server-status')
@login_required
def server_status():
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    load = psutil.getloadavg()
    uptime = time.time() - psutil.boot_time()
    uptime_str = str(datetime.timedelta(seconds=int(uptime)))
    if request.headers.get('HX-Request'):
        return render_partial(SERVER_STATUS_HTML, cpu=cpu, mem=mem, disk=disk, load=load, uptime_str=uptime_str, active_page='server')
    return render_template_string(SERVER_STATUS_HTML, cpu=cpu, mem=mem, disk=disk, load=load, uptime_str=uptime_str, active_page='server')

# ------ Ручные операции ------
@app.route('/manual-ops')
@login_required
def manual_ops():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT id, name FROM campaigns WHERE in_trash=0 ORDER BY name')
    campaigns = c.fetchall()
    c.execute('SELECT id, name FROM landers ORDER BY name')
    landers = c.fetchall()
    c.execute('SELECT id, name FROM offers ORDER BY name')
    offers = c.fetchall()
    conn.close()
    if request.headers.get('HX-Request'):
        return render_partial(MANUAL_OPS_HTML, campaigns=campaigns, landers=landers, offers=offers, active_page='manual')
    return render_template_string(MANUAL_OPS_HTML, campaigns=campaigns, landers=landers, offers=offers, active_page='manual')

@app.route('/manual-ops/add-conversion', methods=['POST'])
@login_required
def add_conversion():
    campaign_id = request.form.get('campaign_id')
    payout = float(request.form.get('payout', 0))
    if not campaign_id: return "Кампания не выбрана", 400
    click_id = f"manual_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}"
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    geo = get_country_by_ip(ip)
    country = geo.get('country', '')
    city = geo.get('city', '')
    ua = request.headers.get('User-Agent', '')
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT lander_id, offer_id FROM campaigns WHERE id=?", (campaign_id,))
    camp = c.fetchone()
    lander_id, offer_id = camp if camp else (None, None)
    c.execute('''INSERT INTO clicks (campaign_id, lander_id, offer_id, click_id, ip, user_agent, country, city)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (campaign_id, lander_id, offer_id, click_id, ip, ua, country, city))
    c.execute('''INSERT INTO leads (campaign_id, offer_id, lander_id, click_id, status, payout)
                 VALUES (?, ?, ?, ?, 'approved', ?)''',
              (campaign_id, offer_id, lander_id, click_id, payout))
    c.execute("INSERT INTO conversions (click_id, payout) VALUES (?, ?)", (click_id, payout))
    conn.commit()
    conn.close()
    return redirect('/manual-ops')

@app.route('/manual-ops/add-spent', methods=['POST'])
@login_required
def add_spent():
    campaign_id = request.form.get('campaign_id')
    amount = float(request.form.get('amount', 0))
    if campaign_id:
        conn = sqlite3.connect(DB)
        conn.execute("UPDATE campaigns SET api_spent = api_spent + ? WHERE id=?", (amount, campaign_id))
        conn.commit()
        conn.close()
    return redirect('/manual-ops')

# ------ Кампании (с тегами, странами, архивом) ------
# ------ Кампании ------
@app.route('/campaigns')
@login_required
@turbo_cache(timeout=60)
def campaigns():
    import time
    t0 = time.time()
    print(f"[CAMPAIGNS] START")
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * PER_PAGE

    filter_tags = request.args.get('tags', '').strip()
    filter_country = request.args.get('country', '').strip()
    show_archived = request.args.get('show_archived', '0') == '1'

    period = request.args.get('period', 'all').strip()
    start_str = request.args.get('start', '').strip()
    end_str = request.args.get('end', '').strip()
    date_from, date_to = get_date_range(period, start_str, end_str)

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    # Базовые условия (корзина, теги, страны)
    where_clauses = ["c.in_trash = 0"]
    params = []

    if filter_tags:
        where_clauses.append("c.tags LIKE ?")
        params.append('%' + filter_tags + '%')
    if filter_country:
        where_clauses.append("c.countries LIKE ?")
        params.append('%"' + filter_country + '"%')

    where_sql = " AND ".join(where_clauses)

    # Параметры для дат: 5 пар = 10 параметров
    if date_from and date_to:
        date_filter_clicks = " AND timestamp BETWEEN ? AND ?"
        date_filter_leads = " AND timestamp BETWEEN ? AND ?"
        date_params = [date_from, date_to] * 5  # 10 значений
    else:
        date_filter_clicks = ""
        date_filter_leads = ""
        date_params = []

    # Общее количество с учётом фильтров (даты не влияют на общее количество кампаний)
    c.execute(f"SELECT COUNT(*) FROM campaigns c WHERE {where_sql}", params)
    total = c.fetchone()[0]

    # Основной запрос с подзапросами статистики за период
# Новый запрос с кэшем и фильтрацией по тегам/странам (без учёта дат)
    c.execute(f'''
        SELECT 
            c.id, c.name, c.params_mapping,
            COALESCE(l.name,'-'), COALESCE(o.name,'-'),
            COALESCE(ts.name,'-'), COALESCE(an.name,'-'),
            c.js_challenge_enabled, c.js_challenge_level, c.domain_id, c.group_id,
            c.tags, c.countries, c.s2s_postback_url, c.ip_blacklist, c.ip_whitelist,
            COALESCE(s.clicks, 0) as clicks,
            COALESCE(s.leads, 0) as total_leads,
            COALESCE(s.approved, 0) as approved,
            COALESCE(s.revenue, 0) as revenue,
            COALESCE(s.cost, 0) as cost
        FROM campaigns c
        LEFT JOIN landers l ON c.lander_id = l.id
        LEFT JOIN offers o ON c.offer_id = o.id
        LEFT JOIN traffic_sources ts ON c.traffic_source_id = ts.id
        LEFT JOIN affiliate_networks an ON c.affiliate_network_id = an.id
        LEFT JOIN campaign_stats s ON c.id = s.campaign_id
        WHERE {where_sql}
        ORDER BY c.id DESC
        LIMIT ? OFFSET ?
    ''', params + [PER_PAGE, offset])
    camps = c.fetchall()

    # Преобразование JSON-строки countries в список + загрузка маппинга макросов
    parsed_camps = []
    mappings = {}  # словарь для хранения маппинга каждой кампании
    for camp in camps:
        camp = list(camp)
        # Защита от None: params_mapping (индекс 2) и теги (индекс 11)
        if camp[2] is None:
            camp[2] = '{}'
        if camp[11] is None:
            camp[11] = ''
        # Загружаем маппинг макросов (индекс 2)
        try:
            mappings[camp[0]] = json_lib.loads(camp[2])
        except:
            mappings[camp[0]] = {}
        # Парсим список стран (индекс 12)
        try:
            camp[12] = json_lib.loads(camp[12]) if camp[12] else []
        except (json_lib.JSONDecodeError, TypeError):
            camp[12] = []
        parsed_camps.append(camp)
    camps = parsed_camps
    t1 = time.time()
    print(f"[CAMPAIGNS] SQL + parse: {t1 - t0:.3f}s")

    # Загрузка справочников
    c.execute('SELECT id, name FROM landers ORDER BY name')
    landers = c.fetchall()
    c.execute('SELECT id, name, default_lander_id FROM offers ORDER BY name')
    offers = c.fetchall()
    c.execute('SELECT id, name FROM traffic_sources ORDER BY name')
    sources = c.fetchall()
    c.execute('SELECT id, name FROM affiliate_networks ORDER BY name')
    networks = c.fetchall()
    c.execute('SELECT id, domain FROM domains ORDER BY is_default DESC, id ASC')
    domains = c.fetchall()
    c.execute('SELECT id, name FROM groups ORDER BY name')
    groups_list = c.fetchall()
    groups_dict = {g[0]: g[1] for g in groups_list}
    conn.close()
    
    t2 = time.time()
    print(f"[CAMPAIGNS] Load dicts: {t2 - t1:.3f}s")
    total_pages = (total + PER_PAGE - 1) // PER_PAGE
    if request.headers.get('HX-Request'):
        return render_partial(CAMPAIGNS_HTML, camps=camps, landers=landers, offers=offers,
                                  sources=sources, networks=networks, domains=domains,
                                  page=page, total_pages=total_pages,
                                  active_page='campaigns', DOMAIN=DOMAIN,
                                  COUNTRY_CODES=COUNTRY_CODES, AVAILABLE_TAGS=AVAILABLE_TAGS, TAG_COLOR_MAP=TAG_COLOR_MAP,
                                  filter_tags=filter_tags, filter_country=filter_country,
                                  show_archived=show_archived,
                                  groups=groups_list, groups_dict=groups_dict,
                                  mappings=mappings,
                                  period=period, start=start_str, end=end_str)
        
    return render_template_string(CAMPAIGNS_HTML, camps=camps, landers=landers, offers=offers,
                                  sources=sources, networks=networks, domains=domains,
                                  page=page, total_pages=total_pages,
                                  active_page='campaigns', DOMAIN=DOMAIN,
                                  COUNTRY_CODES=COUNTRY_CODES, AVAILABLE_TAGS=AVAILABLE_TAGS, TAG_COLOR_MAP=TAG_COLOR_MAP,
                                  filter_tags=filter_tags, filter_country=filter_country,
                                  show_archived=show_archived,
                                  groups=groups_list, groups_dict=groups_dict,
                                  mappings=mappings,
                                  period=period, start=start_str, end=end_str)
@app.route('/campaign/create', methods=['POST'])
@login_required
@admin_required
def create_campaign():
    name = request.form['name'].strip()
    lander_id = request.form.get('lander_id') or None
    offer_id = request.form.get('offer_id') or None
    src_id = request.form.get('source_id') or None
    net_id = request.form.get('network_id') or None
    js_enabled = 1 if request.form.get('js_challenge_enabled') else 0
    js_level = request.form.get('js_challenge_level', 'easy')
    domain_id = request.form.get('domain_id') or None
    group_id = request.form.get('group_id') or None
    tags = request.form.get('tags', '')
    s2s_url = request.form.get('s2s_postback_url', '').strip()
    ip_blacklist = request.form.get('ip_blacklist', '').strip()
    ip_whitelist = request.form.get('ip_whitelist', '').strip()

    countries_list = request.form.getlist('countries_json')
    countries_json = json_lib.dumps(countries_list) if countries_list else '[]'

    # ⬇️ ⬇️ ⬇️ ВОТ ЭТОТ БЛОК ВСТАВЛЯЕМ ⬇️ ⬇️ ⬇️
    # Собираем кастомные макросы
    mapping = {}
    for param in ['cost', 'click_id', 'payout', 'goal'] + [f'sub{i}' for i in range(1, 12)]:
        val = request.form.get(f'macro_{param}', '').strip()
        if val:
            mapping[param] = val
    params_mapping = json.dumps(mapping)
    # ⬆️ ⬆️ ⬆️ КОНЕЦ БЛОКА ⬆️ ⬆️ ⬆️

    conn = sqlite3.connect(DB)
    try:
        conn.execute("INSERT INTO campaigns (name, cpc, lander_id, offer_id, traffic_source_id, affiliate_network_id, js_challenge_enabled, js_challenge_level, domain_id, group_id, tags, countries, s2s_postback_url, ip_blacklist, ip_whitelist, params_mapping) VALUES (?, 0.002, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
             (name, lander_id, offer_id, src_id, net_id, js_enabled, js_level, domain_id, group_id, tags, countries_json, s2s_url, ip_blacklist, ip_whitelist, params_mapping))
        conn.commit()
    except:
        pass
    conn.close()
    return redirect('/campaigns')

@app.route('/campaign/edit/<int:id>', methods=['POST'])
@login_required
@admin_required
def edit_campaign(id):
    name = request.form['name'].strip()
    lander_id = request.form.get('lander_id') or None
    offer_id = request.form.get('offer_id') or None
    src_id = request.form.get('source_id') or None
    net_id = request.form.get('network_id') or None
    js_enabled = 1 if request.form.get('js_challenge_enabled') else 0
    js_level = request.form.get('js_challenge_level', 'easy')
    domain_id = request.form.get('domain_id') or None
    group_id = request.form.get('group_id') or None
    tags = request.form.get('tags', '')
    s2s_url = request.form.get('s2s_postback_url', '').strip()
    ip_blacklist = request.form.get('ip_blacklist', '').strip()
    ip_whitelist = request.form.get('ip_whitelist', '').strip()

    countries_list = request.form.getlist('countries_json')
    countries_json = json_lib.dumps(countries_list) if countries_list else '[]'

    # Собираем кастомные макросы
    mapping = {}
    for param in ['cost', 'click_id', 'payout', 'goal'] + [f'sub{i}' for i in range(1, 12)]:
        val = request.form.get(f'macro_{param}', '').strip()
        if val:
            mapping[param] = val
    params_mapping = json.dumps(mapping)

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    # Обновляем основные поля кампании
    c.execute("UPDATE campaigns SET name=?, lander_id=?, offer_id=?, traffic_source_id=?, affiliate_network_id=?, js_challenge_enabled=?, js_challenge_level=?, domain_id=?, group_id=?, tags=?, countries=?, s2s_postback_url=?, ip_blacklist=?, ip_whitelist=?, params_mapping=? WHERE id=?",
              (name, lander_id, offer_id, src_id, net_id, js_enabled, js_level, domain_id, group_id, tags, countries_json, s2s_url, ip_blacklist, ip_whitelist, params_mapping, id))

    # --- Сохраняем пути (процентный сплит) ---
    path_count = int(request.form.get('path_count', 0))
    c.execute("DELETE FROM rules WHERE campaign_id=? AND condition_type='random'", (id,))
    for i in range(path_count):
        pct = int(request.form.get(f'path_percent_{i}', 0))
        if pct <= 0:
            continue
        path_lander = request.form.get(f'path_lander_{i}') or None
        path_offer = request.form.get(f'path_offer_{i}') or None
        c.execute('''INSERT INTO rules (campaign_id, name, condition_type, operator, value, action, lander_id, offer_id, js_challenge, priority)
                     VALUES (?,?,?,?,?,?,?,?,?,?)''',
                  (id, f'path_{i}', 'random', 'weight', str(pct), 'allow_path', path_lander, path_offer, 0, 0))

    # --- Сохраняем правила клоакинга ---
    rule_count = int(request.form.get('rule_count', 0))
    c.execute("DELETE FROM rules WHERE campaign_id=? AND condition_type!='random'", (id,))
    for i in range(rule_count):
        cond_type = request.form.get(f'rule_condition_type_{i}')
        operator = request.form.get(f'rule_operator_{i}', 'equals')
        value = request.form.get(f'rule_value_{i}', '')
        action = request.form.get(f'rule_action_{i}')
        rule_lander = request.form.get(f'rule_lander_{i}') or None
        rule_offer = request.form.get(f'rule_offer_{i}') or None
        rule_js = 1 if request.form.get(f'rule_js_{i}') else 0
        if not cond_type:
            continue
        c.execute('''INSERT INTO rules (campaign_id, name, condition_type, operator, value, action, lander_id, offer_id, js_challenge, priority)
                     VALUES (?,?,?,?,?,?,?,?,?,?)''',
                  (id, f'rule_{i}', cond_type, operator, value, action, rule_lander, rule_offer, rule_js, 0))

    conn.commit()
    conn.close()
    return redirect('/campaigns')

@app.route('/campaign/edit/<int:id>/form')
@login_required
def edit_campaign_form(id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    # Кампания
    c.execute("SELECT * FROM campaigns WHERE id=?", (id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return "Кампания не найдена", 404

    camp = dict(zip([desc[0] for desc in c.description], row))

    try:
        camp['countries_list'] = json.loads(camp['countries']) if camp['countries'] else []
    except:
        camp['countries_list'] = []

    mapping = {}
    try:
        mapping = json.loads(camp['params_mapping'] or '{}')
    except:
        mapping = {}

    # Справочники (кортежи, не Row)
    c.execute('SELECT id, name FROM landers ORDER BY name')
    landers = c.fetchall()
    c.execute('SELECT id, name FROM offers ORDER BY name')
    offers = c.fetchall()
    c.execute('SELECT id, name FROM traffic_sources ORDER BY name')
    sources = c.fetchall()
    c.execute('SELECT id, name FROM affiliate_networks ORDER BY name')
    networks = c.fetchall()
    c.execute('SELECT id, name FROM groups ORDER BY name')
    groups = c.fetchall()
    c.execute('SELECT id, domain FROM domains ORDER BY is_default DESC, id ASC')
    domains = c.fetchall()

    # Пути и правила (словари)
    c.execute("SELECT * FROM rules WHERE campaign_id=? AND condition_type='random'", (id,))
    paths = [dict(zip([desc[0] for desc in c.description], r)) for r in c.fetchall()]

    c.execute("SELECT * FROM rules WHERE campaign_id=? AND condition_type!='random'", (id,))
    rules = [dict(zip([desc[0] for desc in c.description], r)) for r in c.fetchall()]

    conn.close()

    return render_template_string(
        EDIT_CAMPAIGN_MODAL_HTML,
        camp=camp,
        landers=landers,
        offers=offers,
        sources=sources,
        networks=networks,
        groups=groups,
        domains=domains,
        paths=paths,
        rules=rules,
        mapping=mapping,
        COUNTRY_CODES=COUNTRY_CODES,
        AVAILABLE_TAGS=AVAILABLE_TAGS,
        TAG_COLOR_MAP=TAG_COLOR_MAP
    )

@app.route('/campaign/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_campaign(id):
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE campaigns SET in_trash=1, trashed_at=CURRENT_TIMESTAMP WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash('Кампания перемещена в корзину', 'warning')
    return redirect('/campaigns')

@app.route('/campaign/links/<int:id>')
@login_required
def campaign_links(id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''SELECT c.name, ts.url_template, an.postback_url_template, c.domain_id, c.params_mapping
                 FROM campaigns c
                 LEFT JOIN traffic_sources ts ON c.traffic_source_id=ts.id
                 LEFT JOIN affiliate_networks an ON c.affiliate_network_id=an.id
                 WHERE c.id=?''', (id,))
    camp = c.fetchone()
    if not camp:
        conn.close()
        return "Кампания не найдена", 404
    name, tmpl, ptmpl, domain_id, params_mapping_json = camp

    camp_domain = DOMAIN
    if domain_id:
        c.execute("SELECT domain FROM domains WHERE id=?", (domain_id,))
        dom_row = c.fetchone()
        if dom_row:
            camp_domain = dom_row[0]
    conn.close()

    # --- Загружаем маппинг кастомных макросов ---
    macro = {}
    if params_mapping_json and params_mapping_json.strip():
        try:
            macro = json.loads(params_mapping_json)
        except:
            macro = {}

    # --- Собираем параметры URL с учётом кастомных имён ---
    def param(name, placeholder):
        """
        Если в маппинге задано кастомное имя (например, cost → price),
        то возвращает &price={price} (плейсхолдер совпадает с именем макроса).
        Иначе — пустая строка.
        """
        actual = macro.get(name)
        if not actual:
            return ""
        return f"&{actual}={{{actual}}}"

    # Базовый URL
    if not tmpl:
        base = f"https://{camp_domain}/click?camp={name}"
    else:
        base = tmpl.replace('{host}', camp_domain)

    # click_id и cost — всегда обязательны
    click_macro = param('click_id', 'click_id')
    base += click_macro if click_macro else "&click_id={click_id}"

    cost_macro = param('cost', 'cost')
    base += cost_macro if cost_macro else "&cost={cost}"

    # sub1..sub11 — только если заданы кастомные макросы
    for i in range(1, 12):
        base += param(f'sub{i}', f'sub{i}')

    postback_link = ptmpl
    return f'<p>Клик: <code>{base}</code></p>'

@app.route('/campaigns/bulk-action', methods=['POST'])
@login_required
def campaigns_bulk_action():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Неверные данные'}), 400
    action = data.get('action')
    ids = data.get('ids', [])
    if not ids or not isinstance(ids, list):
        return jsonify({'error': 'Не выбраны кампании'}), 400

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    try:
        if action == 'trash':
            for cid in ids:
                c.execute("UPDATE campaigns SET in_trash=1, trashed_at=CURRENT_TIMESTAMP WHERE id=?", (cid,))
        elif action == 'restore':
            for cid in ids:
                c.execute("UPDATE campaigns SET in_trash=0, trashed_at=NULL WHERE id=?", (cid,))
        elif action == 'destroy':
            for cid in ids:
                c.execute("DELETE FROM clicks WHERE campaign_id=?", (cid,))
                c.execute("DELETE FROM leads WHERE campaign_id=?", (cid,))
                c.execute("DELETE FROM rules WHERE campaign_id=?", (cid,))
                c.execute("DELETE FROM campaigns WHERE id=?", (cid,))
        elif action == 'set_group':
            group_id = data.get('group_id')
            for cid in ids:
                c.execute("UPDATE campaigns SET group_id=? WHERE id=?", (group_id, cid))
            pass
        elif action == 'set_tags':
            tags = data.get('tags', '')
            tag_mode = data.get('tag_mode', 'add')
            for cid in ids:
                if tag_mode == 'replace':
                    c.execute("UPDATE campaigns SET tags=? WHERE id=?", (tags, cid))
                else:  # add
                    c.execute("SELECT tags FROM campaigns WHERE id=?", (cid,))
                    row = c.fetchone()
                    current_tags = row[0] if row else ''
                    current_list = [t.strip() for t in current_tags.split(',') if t.strip()]
                    new_list = [t.strip() for t in tags.split(',') if t.strip()]
                    merged = list(dict.fromkeys(current_list + new_list))  # сохраняем порядок, убираем дубли
                    c.execute("UPDATE campaigns SET tags=? WHERE id=?", (','.join(merged), cid))
        else:
            conn.close()
            return jsonify({'error': 'Неизвестное действие'}), 400
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/campaigns/export-csv')
@login_required
def export_campaigns_csv():
    period = request.args.get('period', 'all').strip()
    start_str = request.args.get('start', '').strip()
    end_str = request.args.get('end', '').strip()
    date_from, date_to = get_date_range(period, start_str, end_str)

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    if date_from and date_to:
        df_clicks = " AND timestamp BETWEEN ? AND ?"
        df_leads = " AND timestamp BETWEEN ? AND ?"
        dp = [date_from, date_to] * 5  # 10 параметров
    else:
        df_clicks = ""
        df_leads = ""
        dp = []

    c.execute(f'''
        SELECT 
            c.id, c.name,
            COALESCE(l.name,''), COALESCE(o.name,''),
            (SELECT COUNT(*) FROM clicks WHERE campaign_id = c.id {df_clicks}) as clicks,
            (SELECT COUNT(*) FROM leads WHERE campaign_id = c.id {df_leads}) as leads,
            (SELECT COUNT(*) FROM leads WHERE campaign_id = c.id AND status='approved' {df_leads}) as approved,
            (SELECT COALESCE(SUM(payout),0) FROM leads WHERE campaign_id = c.id AND status='approved' {df_leads}) as revenue,
            c.cpc * (SELECT COUNT(*) FROM clicks WHERE campaign_id = c.id {df_clicks}) as cost
        FROM campaigns c
        LEFT JOIN landers l ON c.lander_id = l.id
        LEFT JOIN offers o ON c.offer_id = o.id
        WHERE c.in_trash = 0
        ORDER BY c.id DESC
    ''', dp)
    rows = c.fetchall()
    conn.close()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'Name', 'Lander', 'Offer', 'Clicks', 'Leads', 'Approved',
                 'Revenue', 'Cost', 'Profit', 'ROI', 'CPC', 'EPC', 'CR'])
    for r in rows:
        cid, name, lander, offer, clicks, leads, approved, revenue, cost = r
        profit = revenue - cost
        roi = (profit / cost * 100) if cost > 0 else 0
        cpc_val = (cost / clicks) if clicks > 0 else 0
        epc = (revenue / clicks) if clicks > 0 else 0
        cr = (leads / clicks * 100) if clicks > 0 else 0
        cw.writerow([cid, name, lander, offer, clicks, leads, approved,
                     round(revenue, 2), round(cost, 4), round(profit, 2),
                     f"{roi:.1f}%", round(cpc_val, 4), round(epc, 4), f"{cr:.2f}%"])
    output = si.getvalue()
    return Response(output, mimetype="text/csv",
                    headers={"Content-disposition": "attachment; filename=campaigns.csv"})

@app.route('/campaign/new', methods=['GET', 'POST'])
@login_required
def new_campaign():
    if request.method == 'POST':
        name = request.form['name'].strip()
        lander_id = request.form.get('lander_id') or None
        offer_id = request.form.get('offer_id') or None
        src_id = request.form.get('source_id') or None
        net_id = request.form.get('network_id') or None
        domain_id = request.form.get('domain_id') or None
        js_enabled = 1 if request.form.get('js_challenge_enabled') else 0
        js_level = request.form.get('js_challenge_level', 'easy')
        tags = request.form.get('tags', '')
        s2s_url = request.form.get('s2s_postback_url', '').strip()
        countries_json = json.dumps(request.form.getlist('countries_json'))
                # Собираем кастомные макросы
        mapping = {}
        for param in ['cost', 'click_id', 'payout', 'goal'] + [f'sub{i}' for i in range(1, 12)]:
            val = request.form.get(f'macro_{param}', '').strip()
            if val:
                mapping[param] = val
        params_mapping = json.dumps(mapping)

        conn = sqlite3.connect(DB)
        c = conn.cursor()
        try:
            c.execute("SELECT id FROM campaigns WHERE name=?", (name,))
            if c.fetchone():
                conn.close()
                return "Кампания с таким названием уже существует!", 400

            c.execute('''INSERT INTO campaigns 
                (name, cpc, lander_id, offer_id, traffic_source_id, affiliate_network_id,
                 js_challenge_enabled, js_challenge_level, domain_id, tags, countries,
                 s2s_postback_url, params_mapping)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (name, 0.002, lander_id, offer_id, src_id, net_id,
                 js_enabled, js_level, domain_id, tags, countries_json,
                 s2s_url, params_mapping))
            campaign_id = c.lastrowid
            conn.commit()
        except Exception as e:
            conn.close()
            return f"Ошибка: {str(e)}", 500

        # Сохраняем пути (процентный сплит)
        path_count = int(request.form.get('path_count', 0))
        for i in range(path_count):
            pct = int(request.form.get(f'path_percent_{i}', 0))
            if pct <= 0:
                continue
            path_lander = request.form.get(f'path_lander_{i}') or None
            path_offer = request.form.get(f'path_offer_{i}') or None
            c.execute('''INSERT INTO rules (campaign_id, name, condition_type, operator, value, action, lander_id, offer_id, js_challenge, priority)
                         VALUES (?,?,?,?,?,?,?,?,?,?)''',
                      (campaign_id, f'path_{i}', 'random', 'weight', str(pct), 'allow_path', path_lander, path_offer, 0, 0))

        # Сохраняем правила клоакинга
        rule_count = int(request.form.get('rule_count', 0))
        for i in range(rule_count):
            cond_type = request.form.get(f'rule_condition_type_{i}')
            operator = request.form.get(f'rule_operator_{i}', 'equals')
            value = request.form.get(f'rule_value_{i}', '')
            action = request.form.get(f'rule_action_{i}')
            rule_lander = request.form.get(f'rule_lander_{i}') or None
            rule_offer = request.form.get(f'rule_offer_{i}') or None
            rule_js = 1 if request.form.get(f'rule_js_{i}') else 0
            if not cond_type:
                continue
            c.execute('''INSERT INTO rules (campaign_id, name, condition_type, operator, value, action, lander_id, offer_id, js_challenge, priority)
                         VALUES (?,?,?,?,?,?,?,?,?,?)''',
                      (campaign_id, f'rule_{i}', cond_type, operator, value, action, rule_lander, rule_offer, rule_js, 0))

        conn.commit()
        conn.close()
        return redirect('/campaigns')

    # ... (GET-часть остаётся без изменений, но с передачей COUNTRY_CODES)

    # GET — показываем форму
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT id, name FROM landers ORDER BY name')
    landers = c.fetchall()
    c.execute('SELECT id, name FROM offers ORDER BY name')
    offers = c.fetchall()
    c.execute('SELECT id, name FROM traffic_sources ORDER BY name')
    sources = c.fetchall()
    c.execute('SELECT id, name FROM affiliate_networks ORDER BY name')
    networks = c.fetchall()
    c.execute('SELECT id, domain FROM domains ORDER BY is_default DESC, id ASC')
    domains = c.fetchall()
    c.execute('SELECT id, name FROM groups ORDER BY name')
    groups = c.fetchall()
    conn.close
    if request.headers.get('HX-Request'):
        return render_partial(CAMPAIGN_NEW_HTML, landers=landers, offers=offers,
                                  sources=sources, networks=networks, domains=domains,
                                  active_page='campaigns', COUNTRY_CODES=COUNTRY_CODES,
                                  AVAILABLE_TAGS=AVAILABLE_TAGS, TAG_COLOR_MAP=TAG_COLOR_MAP, groups=groups)
    return render_template_string(CAMPAIGN_NEW_HTML, landers=landers, offers=offers,
                                  sources=sources, networks=networks, domains=domains,
                                  active_page='campaigns', COUNTRY_CODES=COUNTRY_CODES,
                                  AVAILABLE_TAGS=AVAILABLE_TAGS, TAG_COLOR_MAP=TAG_COLOR_MAP, groups=groups)

# ============================================================
# API Кампании
# ============================================================
@app.route('/api/campaigns', methods=['GET', 'POST'])
@api_login_required
def api_campaigns():
    if request.method == 'GET':
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute('''SELECT c.id, c.name, c.group_id, c.tags, c.countries, c.is_archived
                     FROM campaigns c WHERE c.in_trash=0 ORDER BY c.id DESC''')
        rows = c.fetchall()
        conn.close()
        result = []
        for r in rows:
            result.append({
                'id': r[0],
                'name': r[1],
                'group_id': r[2],
                'tags': r[3],
                'countries': r[4],
                'is_archived': r[5]
            })
        return jsonify({'success': True, 'data': result})

    # POST — создание кампании
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Неверный JSON'}), 400
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Имя обязательно'}), 400

    lander_id = data.get('lander_id')
    offer_id = data.get('offer_id')
    src_id = data.get('traffic_source_id')
    net_id = data.get('affiliate_network_id')
    domain_id = data.get('domain_id')
    group_id = data.get('group_id')
    tags = data.get('tags', '')
    s2s_url = data.get('s2s_postback_url', '').strip()
    js_enabled = 1 if data.get('js_challenge_enabled') else 0
    js_level = data.get('js_challenge_level', 'easy')
    ip_blacklist = data.get('ip_blacklist', '')
    ip_whitelist = data.get('ip_whitelist', '')
    countries = data.get('countries', [])
    countries_json = json.dumps(countries) if countries else '[]'

    conn = sqlite3.connect(DB)
    try:
        conn.execute("INSERT INTO campaigns (name,cpc,lander_id,offer_id,traffic_source_id,affiliate_network_id,js_challenge_enabled,js_challenge_level,domain_id,group_id,tags,countries,s2s_postback_url,ip_blacklist,ip_whitelist) VALUES (?,0.002,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (name, lander_id, offer_id, src_id, net_id, js_enabled, js_level, domain_id, group_id, tags, countries_json, s2s_url, ip_blacklist, ip_whitelist))
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': new_id})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/campaigns/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@api_login_required
def api_campaign(id):
    if request.method == 'GET':
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute('''SELECT c.* FROM campaigns c WHERE c.id=?''', (id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return jsonify({'error': 'Кампания не найдена'}), 404
        # Вернём все поля (можно урезать)
        columns = [desc[0] for desc in c.description]
        return jsonify({'success': True, 'data': dict(zip(columns, row))})

    if request.method == 'PUT':
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Неверный JSON'}), 400
        # Можно обновлять только переданные поля
        allowed = ['name','lander_id','offer_id','traffic_source_id','affiliate_network_id',
                   'domain_id','group_id','tags','countries','s2s_postback_url',
                   'js_challenge_enabled','js_challenge_level','ip_blacklist','ip_whitelist']
        sets = []
        params = []
        for field in allowed:
            if field in data:
                val = data[field]
                if field == 'countries':
                    val = json.dumps(val) if isinstance(val, list) else val
                sets.append(f"{field}=?")
                params.append(val)
        if not sets:
            return jsonify({'error': 'Нет полей для обновления'}), 400
        params.append(id)
        conn = sqlite3.connect(DB)
        conn.execute(f"UPDATE campaigns SET {','.join(sets)} WHERE id=?", params)
        conn.commit()
        conn.close()
        return jsonify({'success': True})

    if request.method == 'DELETE':
        # Архивация (in_trash=1)
        conn = sqlite3.connect(DB)
        conn.execute("UPDATE campaigns SET in_trash=1, trashed_at=CURRENT_TIMESTAMP WHERE id=?", (id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

@app.route('/api/campaigns/<int:id>/clone', methods=['POST'])
@api_login_required
def api_campaign_clone(id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT * FROM campaigns WHERE id=?", (id,))
    original = c.fetchone()
    if not original:
        conn.close()
        return jsonify({'error': 'Кампания не найдена'}), 404

    columns = [desc[0] for desc in c.description]
    data = dict(zip(columns, original))
    # Убираем id, меняем имя
    data.pop('id')
    data['name'] = data['name'] + ' (копия)'
    # Формируем INSERT динамически (кроме id)
    cols = ', '.join(data.keys())
    placeholders = ', '.join(['?' for _ in data])
    try:
        c.execute(f"INSERT INTO campaigns ({cols}) VALUES ({placeholders})", list(data.values()))
        new_id = c.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': new_id})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/campaigns/<int:id>/restore', methods=['POST'])
@api_login_required
def api_campaign_restore(id):
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE campaigns SET in_trash=0, trashed_at=NULL WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/campaigns/clean_archive', methods=['POST'])
@api_login_required
def api_campaigns_clean_archive():
    conn = sqlite3.connect(DB)
    # Удаляем все кампании в корзине (осторожно!)
    conn.execute("DELETE FROM clicks WHERE campaign_id IN (SELECT id FROM campaigns WHERE in_trash=1)")
    conn.execute("DELETE FROM leads WHERE campaign_id IN (SELECT id FROM campaigns WHERE in_trash=1)")
    conn.execute("DELETE FROM rules WHERE campaign_id IN (SELECT id FROM campaigns WHERE in_trash=1)")
    conn.execute("DELETE FROM campaigns WHERE in_trash=1")
    conn.commit()
    conn.close()
    return jsonify({'success': True})
# ------ Клоакинг и клик ------
def check_rules(campaign_id, environ):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT * FROM rules WHERE campaign_id=? ORDER BY priority', (campaign_id,))
    rules = c.fetchall()
    conn.close()
    ua = environ.get('HTTP_USER_AGENT', '')
    country = environ.get('GEOIP_COUNTRY', '')
    device = 'desktop'
    if 'Mobi' in ua: device = 'mobile'
    elif 'Tablet' in ua: device = 'tablet'
    os = 'other'
    for kw in ['Windows','Android','iOS','Linux','Mac OS X']:
        if kw in ua: os = kw; break
    browser = 'other'
    for kw in ['Chrome','Firefox','Safari','Edge']:
        if kw in ua: browser = kw; break
    connection_type = 'unknown'
    for rule in rules:
        (id,campaign_id,name,cond_type,op,val,action,lander_id,offer_id,js_challenge,priority) = rule
        if cond_type == 'country':
            if op=='equals' and country!=val: continue
            if op=='not_equals' and country==val: continue
        elif cond_type == 'device':
            if op=='equals' and device!=val: continue
            if op=='not_equals' and device==val: continue
        elif cond_type == 'os':
            if op=='equals' and os!=val: continue
            if op=='not_equals' and os==val: continue
        elif cond_type == 'browser':
            if op=='equals' and browser!=val: continue
            if op=='not_equals' and browser==val: continue
        elif cond_type == 'connection_type':
            if op=='equals' and connection_type!=val: continue
            if op=='not_equals' and connection_type==val: continue
        elif cond_type == 'bot_keywords':
            keywords = [k.strip().lower() for k in val.split(',')]
            ua_lower = ua.lower()
            if op=='equals' and not any(k in ua_lower for k in keywords): continue
            if op=='not_equals' and any(k in ua_lower for k in keywords): continue
        return (action, lander_id, offer_id, js_challenge)
    return None

@app.route('/click')
def click():
    campaign_name = request.args.get('camp','')
    click_id = secrets.token_hex(8)
    external_click_id = request.args.get('click_id', '')
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()

    # ЕДИНОЕ ПОДКЛЮЧЕНИЕ НА ВЕСЬ ЗАПРОС
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")

    # --- Глобальная проверка IP ---
    try:
        c.execute("SELECT value FROM settings WHERE key='global_ip_blacklist'")
        row = c.fetchone()
        global_black = row[0].split(',') if row and row[0] else []
        global_black = [x.strip() for x in global_black if x.strip()]

        c.execute("SELECT value FROM settings WHERE key='global_ip_whitelist'")
        row = c.fetchone()
        global_white = row[0].split(',') if row and row[0] else []
        global_white = [x.strip() for x in global_white if x.strip()]

        if ip in global_black:
            conn.close()
            return "Blocked by global blacklist", 403
        if global_white and ip not in global_white:
            conn.close()
            return "Blocked by global whitelist", 403
    except:
        pass

    # --- Проверка чёрного/белого списков кампании ---
    c.execute("SELECT ip_blacklist, ip_whitelist FROM campaigns WHERE name=?", (campaign_name,))
    row = c.fetchone()
    if row:
        black = row[0].split(',') if row[0] else []
        white = row[1].split(',') if row[1] else []
        black = [x.strip() for x in black if x.strip()]
        white = [x.strip() for x in white if x.strip()]
        if ip in black:
            conn.close()
            return "Blocked by blacklist", 403
        if white and ip not in white:
            conn.close()
            return "Blocked by whitelist", 403

    geo = get_country_by_ip(ip)
    country = geo.get('country', '')
    city = geo.get('city', '')
    ua = request.headers.get('User-Agent','')

    # --- Загрузка кампании (с traffic_source_id!) ---
    c.execute("SELECT id, lander_id, offer_id, js_challenge_enabled, js_challenge_level, params_mapping, traffic_source_id FROM campaigns WHERE name=?", (campaign_name,))
    camp = c.fetchone()
    if not camp:
        conn.close()
        return f"Кампания '{campaign_name}' не найдена.", 404
    campaign_id, def_lander_id, def_offer_id, js_enabled, js_level = camp[:5]
    params_mapping_json = camp[5] if len(camp) > 5 else '{}'
    # Получаем traffic_source_id, если он задан, иначе используем 0
    traffic_source_id = camp[6] if len(camp) > 6 and camp[6] else 0

    macro_mapping = {}
    try:
        macro_mapping = json.loads(params_mapping_json or '{}')
    except:
        pass

    # --- Рандомные пути и правила (без изменений) ---
    c.execute("SELECT lander_id, offer_id, value FROM rules WHERE campaign_id=? AND condition_type='random' AND operator='weight'", (campaign_id,))
    random_rules = c.fetchall()

    if random_rules:
        total_weight = sum(int(r[2]) for r in random_rules if r[2])
        if total_weight > 0:
            import random
            rnd = random.randint(1, total_weight)
            current = 0
            chosen_lander = def_lander_id
            chosen_offer = def_offer_id
            for r in random_rules:
                weight = int(r[2])
                current += weight
                if rnd <= current:
                    chosen_lander = r[0] if r[0] else def_lander_id
                    chosen_offer = r[1] if r[1] else def_offer_id
                    break
            final_lander = chosen_lander
            final_offer = chosen_offer
            need_js = js_enabled
            rule_used = False
        else:
            rule_used = False
    else:
        rule_used = False

    if not rule_used and not random_rules:
        environ = {'REMOTE_ADDR': ip, 'HTTP_USER_AGENT': ua, 'GEOIP_COUNTRY': country}
        rule_result = check_rules(campaign_id, environ)
        if rule_result:
            action, lander_id, offer_id, rule_js = rule_result
            if action == 'block':
                conn.close()
                return "Blocked", 403
            final_lander = lander_id if lander_id else def_lander_id
            final_offer = offer_id if offer_id else def_offer_id
            need_js = js_enabled or rule_js
        else:
            final_lander = def_lander_id
            final_offer = def_offer_id
            need_js = js_enabled
    elif not random_rules:
        environ = {'REMOTE_ADDR': ip, 'HTTP_USER_AGENT': ua, 'GEOIP_COUNTRY': country}
        rule_result = check_rules(campaign_id, environ)
        if rule_result:
            action, lander_id, offer_id, rule_js = rule_result
            if action == 'block':
                conn.close()
                return "Blocked", 403
            final_lander = lander_id if lander_id else def_lander_id
            final_offer = offer_id if offer_id else def_offer_id
            need_js = js_enabled or rule_js
        else:
            final_lander = def_lander_id
            final_offer = def_offer_id
            need_js = js_enabled

    # --- Запись клика ---
    sub_values = []
    for i in range(1, 12):
        param_name = macro_mapping.get(f'sub{i}', f'sub{i}')
        sub_values.append(request.args.get(param_name, '').strip())

    try:
        c.execute('''INSERT INTO clicks 
            (campaign_id, lander_id, offer_id, click_id, ip, user_agent, country, city, external_click_id,
             sub1, sub2, sub3, sub4, sub5, sub6, sub7, sub8, sub9, sub10, sub11)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            [campaign_id, final_lander, final_offer, click_id, ip, ua, country, city, external_click_id] + sub_values)
        conn.commit()
    except Exception as e:
        with open('/tmp/click_error.log', 'a') as f:
            f.write(f"{datetime.datetime.now()} - {e}\n")
        conn.rollback()


    # --- Сохранение расхода (с макросом) ---
    cost_param = macro_mapping.get('cost', 'cost')
    cost = request.args.get(cost_param, '').strip()
    if cost:
        try:
            cost_val = float(cost)
            date_str = datetime.datetime.now().strftime('%Y-%m-%d')
            # Теперь передаём click_id и правильный traffic_source_id
            c.execute('''INSERT OR IGNORE INTO traffic_costs (traffic_source_id, campaign_id, date, cost, source_type, click_id)
                         VALUES (?, ?, ?, ?, 'url', ?)''',
                      (traffic_source_id, campaign_id, date_str, cost_val, click_id))
            c.execute("UPDATE campaigns SET api_spent = api_spent + ? WHERE id=?", (cost_val, campaign_id))
            conn.commit()
        except (ValueError, TypeError):
            pass

    # --- Лендинг или оффер ---
    lander_url = ''
    if final_lander:
        c.execute("SELECT type, url, file_path, index_file FROM landers WHERE id=?", (final_lander,))
        lander = c.fetchone()
        if lander:
            if lander[0] == 'file' and lander[2]:
                index_file = lander[3] if lander[3] else 'index.html'
                lander_url = f"http://{request.host}/lander/{final_lander}/{index_file}"
            else:
                lander_url = lander[1]
    elif final_offer:
        c.execute("SELECT url FROM offers WHERE id=?", (final_offer,))
        offer_row = c.fetchone()
        if offer_row and offer_row[0]:
            lander_url = offer_row[0]
            if '?' in lander_url:
                lander_url += '&sub1=' + click_id
            else:
                lander_url += '?sub1=' + click_id

    conn.close()

    if not lander_url:
        lander_url = "https://example.com"

    if need_js:
        complexity = {'super_easy': 10000, 'easy': 50000, 'medium': 200000}.get(js_level, 50000)
        a = secrets.randbelow(complexity)
        b = secrets.randbelow(complexity)
        challenge = f"{a}+{b}"
        expected = str(a + b)
        return render_template_string(CHALLENGE_HTML, click_id=click_id, lander_url=lander_url,
                                      challenge=challenge, expected=expected)
    else:
        return redirect(f"{lander_url}?click_id={click_id}", 302)

@app.route('/postback')
def postback():
    # 1. Чистим click_id от возможного мусора в URL
    raw_click_id = request.args.get('click_id', '')
    if '?click_id=' in raw_click_id:
        click_id = raw_click_id.split('?click_id=')[-1].split('&')[0]
    else:
        click_id = raw_click_id

    # 2. Получаем выплату и цель
    try:
        payout = float(request.args.get('payout', 0))
    except (ValueError, TypeError):
        payout = 0.0

    goal = request.args.get('goal', 'default').strip()
    ip = request.remote_addr
    raw_url = request.url
    raw_params = request.query_string.decode()  # сохраним все параметры для логов

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("PRAGMA busy_timeout = 5000")

    # ---- ЛОГИРОВАНИЕ: записываем вызов -----
    campaign_id_log = None
    offer_id_log = None
    c.execute("SELECT campaign_id, offer_id FROM clicks WHERE click_id=?", (click_id,))
    click_row = c.fetchone()
    if click_row:
        campaign_id_log, offer_id_log = click_row

    c.execute('''INSERT INTO postback_log (click_id, payout, status, raw_url, ip, campaign_id, offer_id, raw_params)
                 VALUES (?, ?, 'received', ?, ?, ?, ?, ?)''',
              (click_id, payout, raw_url, ip, campaign_id_log, offer_id_log, raw_params))
    log_id = c.lastrowid
    conn.commit()
    # ----------------------------------------

    # 3. Ищем клик по нашему внутреннему click_id
    c.execute("SELECT campaign_id, offer_id, lander_id, external_click_id FROM clicks WHERE click_id=?", (click_id,))
    click_row = c.fetchone()

    campaign_id = offer_id = lander_id = external_click_id = None
    if click_row:
        campaign_id, offer_id, lander_id, external_click_id = click_row

    # 4. Вставляем лид (только один раз), а если уже есть – просто обновляем данные,
    #    НЕ сбрасывая s2s_sent!
    c.execute("INSERT OR IGNORE INTO leads (campaign_id, offer_id, lander_id, click_id, status, payout, goal, s2s_sent) VALUES (?, ?, ?, ?, 'approved', ?, ?, 0)",
              (campaign_id or 0, offer_id or 0, lander_id or 0, click_id, payout, goal))

    # Если лид уже существовал (был конфликт), обновим выплату и цель, но оставим s2s_sent как есть
    if c.rowcount == 0:
        c.execute("UPDATE leads SET payout = ?, goal = ?, status = 'approved' WHERE click_id = ?",
                  (payout, goal, click_id))

    conn.commit()

    # 5. Записываем конверсию (уникальность по click_id)
    c.execute("INSERT OR IGNORE INTO conversions (click_id, payout) VALUES (?, ?)", (click_id, payout))
    conn.commit()

    # 6. Обновляем сабы в клике, если они переданы
    for i in range(1, 12):
        sub_val = request.args.get(f'sub{i}', '').strip()
        if sub_val:
            c.execute(f"UPDATE clicks SET sub{i}=? WHERE click_id=?", (sub_val, click_id))
    conn.commit()

    # 7. Отправляем S2S постбек в источник, только если ещё не отправляли и есть external_click_id
    c.execute("SELECT s2s_sent FROM leads WHERE click_id=?", (click_id,))
    row = c.fetchone()
    s2s_sent = row[0] if row else 1

    if not s2s_sent and campaign_id and external_click_id:
        c.execute("SELECT s2s_postback_url FROM campaigns WHERE id=?", (campaign_id,))
        camp_row = c.fetchone()
        if camp_row and camp_row[0]:
            s2s_url = camp_row[0]
            final_url = s2s_url.replace('{click_id}', external_click_id).replace('{payout}', str(payout))
            try:
                requests.get(final_url, timeout=3)
                c.execute("UPDATE leads SET s2s_sent = 1 WHERE click_id = ?", (click_id,))
                conn.commit()
            except:
                pass  # если не удалось, не меняем флаг – попробуем при следующем постбеке

    # ---- ОБНОВЛЯЕМ СТАТУС ЛОГА НА УСПЕХ -----
    c.execute("UPDATE postback_log SET status='processed' WHERE id=?", (log_id,))
    conn.commit()
    conn.close()
    return "OK", 200

@app.route('/cost-postback')
def cost_postback():
    source_id = request.args.get('source_id', '').strip()
    campaign_id = request.args.get('campaign_id', '').strip()
    click_id = request.args.get('click_id', '').strip()
    cost = request.args.get('cost', '0').strip()
    impressions = request.args.get('impressions', '0').strip()
    clicks = request.args.get('clicks', '0').strip()

    # Если source_id не передан, пробуем вытащить его из клика по click_id
    if not source_id and click_id:
        try:
            conn = sqlite3.connect(DB)
            c = conn.cursor()
            c.execute("SELECT campaign_id FROM clicks WHERE click_id=?", (click_id,))
            row = c.fetchone()
            if row:
                campaign_id = row[0]  # используем campaign_id как traffic_source_id, если у тебя так настроено
                source_id = row[0]  # или можно поставить 0, если отдельный source_id не нужен
            conn.close()
        except:
            pass
    # Если всё равно пусто — ставим 0, чтобы запись прошла
    if not source_id:
        source_id = '0'

    try:
        cost_val = float(cost)
        imp_val = int(impressions) if impressions else 0
        click_val = int(clicks) if clicks else 0
        date_str = datetime.datetime.now().strftime('%Y-%m-%d')

        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute('''INSERT OR IGNORE INTO traffic_costs 
                     (traffic_source_id, campaign_id, date, cost, impressions, clicks, source_type, click_id)
                     VALUES (?, ?, ?, ?, ?, ?, 'postback', ?)''',
                  (source_id, campaign_id or None, date_str, cost_val, imp_val, click_val, click_id))
        conn.commit()
        conn.close()
        return "OK", 200
    except Exception as e:
        return f"Error: {e}", 400

@app.route('/offer/<int:offer_id>/default-lander')
def get_default_lander(offer_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT default_lander_id FROM offers WHERE id=?", (offer_id,))
    row = c.fetchone()
    conn.close()
    return jsonify({'lander_id': row[0] if row and row[0] else None})

# =============== API OFFERS ===============
@app.route('/api/offers', methods=['GET','POST'])
@api_login_required
def api_offers():
    if request.method == 'GET':
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("SELECT id, name, group_id, affiliate_network_id, url, payout, country, tags FROM offers WHERE in_trash=0 ORDER BY id DESC")
        rows = c.fetchall()
        conn.close()
        return jsonify({'success':True, 'data': [dict(zip(['id','name','group_id','affiliate_network_id','url','payout','country','tags'], r)) for r in rows]})

    data = request.get_json()
    name = data.get('name','').strip()
    if not name: return jsonify({'error':'Name required'}), 400
    fields = ['name','group_id','affiliate_network_id','url','payout','country','tags']
    vals = [data.get(f) for f in fields]
    vals[0] = name
    conn = sqlite3.connect(DB)
    try:
        conn.execute(f"INSERT INTO offers ({','.join(fields)}) VALUES ({','.join(['?']*len(fields))})", vals)
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        conn.close()
        return jsonify({'success':True, 'id':new_id})
    except Exception as e:
        conn.close(); return jsonify({'error':str(e)}), 500

@app.route('/api/offers/<int:id>', methods=['GET','PUT','DELETE'])
@api_login_required
def api_offer(id):
    if request.method == 'GET':
        conn = sqlite3.connect(DB); c = conn.cursor()
        c.execute("SELECT * FROM offers WHERE id=?", (id,))
        row = c.fetchone()
        conn.close()
        if not row: return jsonify({'error':'Not found'}), 404
        cols = [desc[0] for desc in c.description]
        return jsonify({'success':True, 'data': dict(zip(cols, row))})

    if request.method == 'PUT':
        data = request.get_json()
        allowed = ['name','group_id','affiliate_network_id','url','payout','country','tags','cap_enabled','cap_clicks','cap_conversions','cap_reset_period_hours','cap_reset_time_utc3','reserve_offer_id','default_lander_id']
        sets, params = [], []
        for f in allowed:
            if f in data:
                sets.append(f"{f}=?"); params.append(data[f])
        if not sets: return jsonify({'error':'No fields'}), 400
        params.append(id)
        conn = sqlite3.connect(DB)
        conn.execute(f"UPDATE offers SET {','.join(sets)} WHERE id=?", params)
        conn.commit()
        conn.close()
        return jsonify({'success':True})

    if request.method == 'DELETE':
        conn = sqlite3.connect(DB)
        conn.execute("UPDATE offers SET in_trash=1, trashed_at=CURRENT_TIMESTAMP WHERE id=?", (id,))
        conn.commit()
        conn.close()
        return jsonify({'success':True})

# Аналогично добавьте клонирование, восстановление, очистку архива (шаблон тот же, что у лендингов)
# ------ Клик-лог и CSV-экспорт ------
@app.route('/clicklog')
@login_required
def clicklog():
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * PER_PAGE

    search_q = request.args.get('q', '').strip()
    search_ip = request.args.get('ip', '').strip()

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT id, name FROM campaigns ORDER BY name')
    campaigns = c.fetchall()

    # Динамический WHERE для поиска
    where_clauses = []
    params = []
    if search_q:
        where_clauses.append("(cl.click_id LIKE ? OR cl.external_click_id LIKE ?)")
        like_q = '%' + search_q + '%'
        params.extend([like_q, like_q])
    if search_ip:
        where_clauses.append("cl.ip LIKE ?")
        params.append('%' + search_ip + '%')

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    # Общее количество
    c.execute(f"SELECT COUNT(*) FROM clicks cl WHERE {where_sql}", params)
    total = c.fetchone()[0]

    # Основной запрос — теперь выбираем sub1…sub11
    c.execute(f'''
        SELECT c.name, COALESCE(l.name,'-'), COALESCE(o.name,'-'),
               cl.click_id, cl.ip, cl.user_agent, cl.country, cl.city,
               cl.timestamp, conv.payout, cl.external_click_id,
               cl.sub1, cl.sub2, cl.sub3, cl.sub4, cl.sub5,
               cl.sub6, cl.sub7, cl.sub8, cl.sub9, cl.sub10, cl.sub11
        FROM clicks cl
        JOIN campaigns c ON cl.campaign_id = c.id
        LEFT JOIN landers l ON cl.lander_id = l.id
        LEFT JOIN offers o ON cl.offer_id = o.id
        LEFT JOIN conversions conv ON cl.click_id = conv.click_id
        WHERE {where_sql}
        ORDER BY cl.timestamp DESC
        LIMIT ? OFFSET ?
    ''', params + [PER_PAGE, offset])
    rows = c.fetchall()
    conn.close()

    total_pages = (total + PER_PAGE - 1) // PER_PAGE
    if request.headers.get('HX-Request'):
        return render_partial(CLICKLOG_HTML, rows=rows, page=page,
                                  total_pages=total_pages,
                                  active_page='clicklog', campaigns=campaigns,
                                  search_q=search_q, search_ip=search_ip)
    return render_template_string(CLICKLOG_HTML, rows=rows, page=page,
                                  total_pages=total_pages,
                                  active_page='clicklog', campaigns=campaigns,
                                  search_q=search_q, search_ip=search_ip)

@app.route('/clicklog/export')
@login_required
def clicklog_export():
    campaign_id = request.args.get('campaign_id', '')
    lander_id = request.args.get('lander_id', '')
    offer_id = request.args.get('offer_id', '')
    start_date = request.args.get('start', '')
    end_date = request.args.get('end', '')

    query = '''SELECT c.name, cl.ip, cl.user_agent, cl.country, cl.city,
                      cl.timestamp, conv.payout, cl.click_id, cl.external_click_id
               FROM clicks cl
               JOIN campaigns c ON cl.campaign_id = c.id
               LEFT JOIN conversions conv ON cl.click_id = conv.click_id
               WHERE 1=1'''
    params = []
    if campaign_id:
        query += " AND c.id = ?"
        params.append(campaign_id)
    if lander_id:
        query += " AND cl.lander_id = ?"
        params.append(lander_id)
    if offer_id:
        query += " AND cl.offer_id = ?"
        params.append(offer_id)
    if start_date:
        query += " AND cl.timestamp >= ?"
        params.append(start_date + " 00:00:00")
    if end_date:
        query += " AND cl.timestamp <= ?"
        params.append(end_date + " 23:59:59")

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Campaign', 'IP', 'User-Agent', 'Country', 'City', 'Timestamp', 'Payout', 'Click ID', 'External Click ID'])
    cw.writerows(rows)
    output = si.getvalue()
    return Response(output, mimetype="text/csv",
                    headers={"Content-disposition": "attachment; filename=clicklog.csv"})

@app.route('/clicklog/export-ips')
@login_required
def clicklog_export_ips():
    campaign_id = request.args.get('campaign_id', 'all').strip()

    query = "SELECT DISTINCT cl.ip FROM clicks cl JOIN campaigns c ON cl.campaign_id = c.id WHERE 1=1"
    params = []
    if campaign_id != 'all':
        query += " AND c.id = ?"
        params.append(campaign_id)

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    output = "\n".join([row[0] for row in rows])
    return Response(output, mimetype="text/plain",
                    headers={"Content-disposition": "attachment; filename=ips.txt"})
# ------ Лендинги (с HTML-кодом) ------
@app.route('/lander/<int:lander_id>/<path:filename>')
def serve_lander(lander_id,filename):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT file_path FROM landers WHERE id=? AND type='file'",(lander_id,))
    row = c.fetchone()
    conn.close()
    if row:
        folder = os.path.join(UPLOAD_FOLDER,str(lander_id))
        return send_from_directory(folder,filename)
    return "Not found",404

@app.route('/landers')
@login_required
def landers():
    period = request.args.get('period', 'all').strip()
    start_str = request.args.get('start', '').strip()
    end_str = request.args.get('end', '').strip()
    date_from, date_to = get_date_range(period, start_str, end_str)

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT id,name,group_id,url,language,type,index_file,tags FROM landers WHERE is_archived=0 AND in_trash=0 ORDER BY name')
    landers_list = c.fetchall()
    c.execute('SELECT id,name FROM groups ORDER BY name')
    groups_list = c.fetchall()

    if date_from and date_to:
        df_clicks = " AND timestamp BETWEEN ? AND ?"
        df_leads = " AND timestamp BETWEEN ? AND ?"
        dp = [date_from, date_to] * 5
    else:
        df_clicks = ""
        df_leads = ""
        dp = []

    c.execute(f'''
        SELECT 
            l.id,
            COALESCE(SUM(c.clicks), 0) as clicks,
            COALESCE(SUM(c.leads), 0) as leads,
            COALESCE(SUM(c.approved), 0) as approved,
            COALESCE(SUM(c.revenue), 0) as revenue,
            COALESCE(SUM(c.cost), 0) as cost
        FROM landers l
        LEFT JOIN (
            SELECT 
                lander_id,
                (SELECT COUNT(*) FROM clicks WHERE campaign_id = c.id {df_clicks}) as clicks,
                (SELECT COUNT(*) FROM leads WHERE campaign_id = c.id {df_leads}) as leads,
                (SELECT COUNT(*) FROM leads WHERE campaign_id = c.id AND status='approved' {df_leads}) as approved,
                (SELECT COALESCE(SUM(payout),0) FROM leads WHERE campaign_id = c.id AND status='approved' {df_leads}) as revenue,
                c.cpc * (SELECT COUNT(*) FROM clicks WHERE campaign_id = c.id {df_clicks}) as cost
            FROM campaigns c
            WHERE c.lander_id IS NOT NULL
        ) c ON c.lander_id = l.id
        GROUP BY l.id
    ''', dp)
    stats_raw = c.fetchall()
    conn.close()

    stats = {}
    for row in stats_raw:
        lid, clicks, leads, approved, revenue, cost = row
        stats[lid] = {
            'clicks': clicks, 'leads': leads, 'approved': approved,
            'revenue': revenue or 0.0, 'cost': cost or 0.0
        }
    for lander in landers_list:
        if lander[0] not in stats:
            stats[lander[0]] = {'clicks':0, 'leads':0, 'approved':0, 'revenue':0.0, 'cost':0.0}

    groups_dict = {g[0]: g[1] for g in groups_list}
    if request.headers.get('HX-Request'):
        return render_partial(LANDERS_HTML, landers=landers_list, groups=groups_list,
                      stats=stats, groups_dict=groups_dict,
                      active_page='landers', AVAILABLE_TAGS=AVAILABLE_TAGS,
                      TAG_COLOR_MAP=TAG_COLOR_MAP,
                      period=period, start=start_str, end=end_str)
    return render_template_string(LANDERS_HTML, landers=landers_list, groups=groups_list,
                                  stats=stats, groups_dict=groups_dict,
                                  active_page='landers', AVAILABLE_TAGS=AVAILABLE_TAGS,
                                  TAG_COLOR_MAP=TAG_COLOR_MAP,
                                  period=period, start=start_str, end=end_str)

@app.route('/lander/create', methods=['POST'])
@login_required
@admin_required
def create_lander():
    name = request.form['name'].strip()
    group_id = request.form.get('group_id') or None
    url = request.form.get('url','').strip()
    language = request.form.get('language','').strip()
    ltype = request.form.get('type','url')
    index_file = request.form.get('index_file','index.html').strip() or 'index.html'
    tags = request.form.get('tags','')
    html_code = request.form.get('html_code','')

    if ltype == 'html' and html_code:
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("INSERT INTO landers (name,group_id,type,file_path,index_file,tags) VALUES (?,?,'file','',?,?)",
                  (name, group_id, index_file, tags))
        lander_id = c.lastrowid
        dest = os.path.join(UPLOAD_FOLDER, str(lander_id))
        os.makedirs(dest, exist_ok=True)
        with open(os.path.join(dest, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(html_code)
        c.execute("UPDATE landers SET file_path=? WHERE id=?", (dest, lander_id))
        conn.commit()
        conn.close()
        return redirect('/landers')

    if ltype == 'file':
        uploaded = request.files.get('file')
        if not uploaded or not uploaded.filename: return "Файл не выбран", 400
        tmp_zip = os.path.join(UPLOAD_FOLDER, f'tmp_{secrets.token_hex(4)}.zip')
        uploaded.save(tmp_zip)
        try:
            import zipfile
            if not zipfile.is_zipfile(tmp_zip):
                os.remove(tmp_zip)
                return "Файл не является ZIP-архивом", 400
            conn = sqlite3.connect(DB)
            c = conn.cursor()
            c.execute("INSERT INTO landers (name,group_id,type,file_path,index_file,tags) VALUES (?,?,'file','',?,?)",
                      (name, group_id, index_file, tags))
            lander_id = c.lastrowid
            dest = os.path.join(UPLOAD_FOLDER, str(lander_id))
            os.makedirs(dest, exist_ok=True)
            with zipfile.ZipFile(tmp_zip, 'r') as z: z.extractall(dest)
            c.execute("UPDATE landers SET file_path=? WHERE id=?", (dest, lander_id))
            conn.commit()
            conn.close()
            os.remove(tmp_zip)
            return redirect('/landers')
        except Exception as e:
            if os.path.exists(tmp_zip): os.remove(tmp_zip)
            return f"Ошибка при распаковке: {str(e)}", 500

    conn = sqlite3.connect(DB)
    try:
        conn.execute("INSERT INTO landers (name,group_id,url,language,type,index_file,tags) VALUES (?,?,?,?,?,?,?)",
                     (name, group_id, url, language, ltype, index_file, tags))
        conn.commit()
    except: pass
    conn.close()
    return redirect('/landers')

@app.route('/lander/edit/<int:id>', methods=['POST'])
@login_required
@admin_required
def edit_lander(id):
    name = request.form['name'].strip()
    group_id = request.form.get('group_id') or None
    url = request.form.get('url','').strip()
    language = request.form.get('language','').strip()
    index_file = request.form.get('index_file','index.html').strip() or 'index.html'
    tags = request.form.get('tags','')
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE landers SET name=?, group_id=?, url=?, language=?, index_file=?, tags=? WHERE id=?",
                 (name, group_id, url, language, index_file, tags, id))
    conn.commit()
    conn.close()
    return redirect('/landers')

@app.route('/landers/export-csv')
@login_required
def export_landers_csv():
    period = request.args.get('period', 'all').strip()
    start_str = request.args.get('start', '').strip()
    end_str = request.args.get('end', '').strip()
    date_from, date_to = get_date_range(period, start_str, end_str)

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    if date_from and date_to:
        df_clicks = " AND timestamp BETWEEN ? AND ?"
        df_leads = " AND timestamp BETWEEN ? AND ?"
        dp = [date_from, date_to] * 5
    else:
        df_clicks = ""
        df_leads = ""
        dp = []

    c.execute(f'''
        SELECT l.id, l.name,
            COALESCE(SUM(c.clicks),0), COALESCE(SUM(c.leads),0),
            COALESCE(SUM(c.approved),0), COALESCE(SUM(c.revenue),0),
            COALESCE(SUM(c.cost),0)
        FROM landers l
        LEFT JOIN (
            SELECT lander_id,
                (SELECT COUNT(*) FROM clicks WHERE campaign_id = c.id {df_clicks}) as clicks,
                (SELECT COUNT(*) FROM leads WHERE campaign_id = c.id {df_leads}) as leads,
                (SELECT COUNT(*) FROM leads WHERE campaign_id = c.id AND status='approved' {df_leads}) as approved,
                (SELECT COALESCE(SUM(payout),0) FROM leads WHERE campaign_id = c.id AND status='approved' {df_leads}) as revenue,
                c.cpc * (SELECT COUNT(*) FROM clicks WHERE campaign_id = c.id {df_clicks}) as cost
            FROM campaigns c WHERE c.lander_id IS NOT NULL
        ) c ON c.lander_id = l.id
        WHERE l.in_trash=0
        GROUP BY l.id
    ''', dp)
    rows = c.fetchall()
    conn.close()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID','Name','Clicks','Leads','Approved','Revenue','Cost','Profit','ROI','CPC','EPC','CR'])
    for r in rows:
        lid, name, clicks, leads, approved, revenue, cost = r
        profit = revenue - cost
        roi = (profit / cost * 100) if cost > 0 else 0
        cpc_val = (cost / clicks) if clicks > 0 else 0
        epc = (revenue / clicks) if clicks > 0 else 0
        cr = (leads / clicks * 100) if clicks > 0 else 0
        cw.writerow([lid, name, clicks, leads, approved, round(revenue,2), round(cost,4),
                     round(profit,2), f"{roi:.1f}%", round(cpc_val,4), round(epc,4), f"{cr:.2f}%"])
    return Response(si.getvalue(), mimetype="text/csv",
                    headers={"Content-disposition": "attachment; filename=landers.csv"})

@app.route('/lander/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_lander(id):
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE landers SET in_trash=1, trashed_at=CURRENT_TIMESTAMP WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash('Лендинг перемещён в корзину', 'warning')
    return redirect('/landers')

    # POST — создание
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Имя обязательно'}), 400
    group_id = data.get('group_id')
    url = data.get('url', '')
    ltype = data.get('type', 'url')
    tags = data.get('tags', '')

    conn = sqlite3.connect(DB)
    try:
        conn.execute("INSERT INTO landers (name, group_id, url, type, tags) VALUES (?,?,?,?,?)",
                     (name, group_id, url, ltype, tags))
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': new_id})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500

# =============== API LANDERS ===============
@app.route('/api/landers', methods=['GET', 'POST'])
@api_login_required
def api_landers():
    if request.method == 'GET':
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("SELECT id, name, group_id, url, type, tags FROM landers WHERE in_trash=0 ORDER BY id DESC")
        rows = c.fetchall()
        conn.close()
        return jsonify({'success': True, 'data': [dict(zip(['id','name','group_id','url','type','tags'], r)) for r in rows]})

    data = request.get_json()
    if not data: return jsonify({'error':'Invalid JSON'}), 400
    name = data.get('name','').strip()
    if not name: return jsonify({'error':'Name required'}), 400
    group_id = data.get('group_id')
    url = data.get('url','')
    ltype = data.get('type','url')
    tags = data.get('tags','')

    conn = sqlite3.connect(DB)
    try:
        conn.execute("INSERT INTO landers (name,group_id,url,type,tags) VALUES (?,?,?,?,?)",
                     (name, group_id, url, ltype, tags))
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        conn.close()
        return jsonify({'success':True, 'id':new_id})
    except Exception as e:
        conn.close()
        return jsonify({'error':str(e)}), 500

@app.route('/api/landers/<int:id>', methods=['GET','PUT','DELETE'])
@api_login_required
def api_lander(id):
    if request.method == 'GET':
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("SELECT * FROM landers WHERE id=?", (id,))
        row = c.fetchone()
        conn.close()
        if not row: return jsonify({'error':'Not found'}), 404
        cols = [desc[0] for desc in c.description]
        return jsonify({'success':True, 'data': dict(zip(cols, row))})

    if request.method == 'PUT':
        data = request.get_json()
        allowed = ['name','group_id','url','type','tags','language','index_file']
        sets, params = [], []
        for f in allowed:
            if f in data:
                sets.append(f"{f}=?"); params.append(data[f])
        if not sets: return jsonify({'error':'No fields'}), 400
        params.append(id)
        conn = sqlite3.connect(DB)
        conn.execute(f"UPDATE landers SET {','.join(sets)} WHERE id=?", params)
        conn.commit()
        conn.close()
        return jsonify({'success':True})

    if request.method == 'DELETE':
        conn = sqlite3.connect(DB)
        conn.execute("UPDATE landers SET in_trash=1, trashed_at=CURRENT_TIMESTAMP WHERE id=?", (id,))
        conn.commit()
        conn.close()
        return jsonify({'success':True})

@app.route('/api/landers/<int:id>/clone', methods=['POST'])
@api_login_required
def api_lander_clone(id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT * FROM landers WHERE id=?", (id,))
    orig = c.fetchone()
    if not orig: conn.close(); return jsonify({'error':'Not found'}), 404
    cols = [d[0] for d in c.description]
    data = dict(zip(cols, orig))
    data.pop('id'); data['name'] += ' (копия)'
    try:
        c.execute(f"INSERT INTO landers ({','.join(data.keys())}) VALUES ({','.join(['?']*len(data))})", list(data.values()))
        new_id = c.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'success':True, 'id':new_id})
    except Exception as e:
        conn.close(); return jsonify({'error':str(e)}), 500

@app.route('/api/landers/<int:id>/restore', methods=['POST'])
@api_login_required
def api_lander_restore(id):
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE landers SET in_trash=0, trashed_at=NULL WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return jsonify({'success':True})

@app.route('/api/landers/clean_archive', methods=['POST'])
@api_login_required
def api_landers_clean_archive():
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM landers WHERE in_trash=1")
    conn.commit()
    conn.close()
    return jsonify({'success':True})
# ------ Офферы ------
@app.route('/offers')
@login_required
def offers():
    period = request.args.get('period', 'all').strip()
    start_str = request.args.get('start', '').strip()
    end_str = request.args.get('end', '').strip()
    date_from, date_to = get_date_range(period, start_str, end_str)

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT id,name,group_id,affiliate_network_id,url,payout,country,cap_enabled,cap_clicks,cap_conversions,cap_reset_period_hours,cap_reset_time_utc3,reserve_offer_id,default_lander_id,tags FROM offers WHERE is_archived=0 AND in_trash=0 ORDER BY name')
    offers_list = c.fetchall()
    c.execute('SELECT id,name FROM groups ORDER BY name')
    groups_list = c.fetchall()
    c.execute('SELECT id,name FROM affiliate_networks ORDER BY name')
    networks = c.fetchall()
    c.execute('SELECT id,name FROM landers ORDER BY name')
    landers = c.fetchall()

    if date_from and date_to:
        df_clicks = " AND timestamp BETWEEN ? AND ?"
        df_leads = " AND timestamp BETWEEN ? AND ?"
        dp = [date_from, date_to] * 5
    else:
        df_clicks = ""
        df_leads = ""
        dp = []

    c.execute(f'''
        SELECT 
            o.id,
            COALESCE(SUM(c.clicks), 0) as clicks,
            COALESCE(SUM(c.leads), 0) as leads,
            COALESCE(SUM(c.approved), 0) as approved,
            COALESCE(SUM(c.revenue), 0) as revenue,
            COALESCE(SUM(c.cost), 0) as cost
        FROM offers o
        LEFT JOIN (
            SELECT 
                offer_id,
                (SELECT COUNT(*) FROM clicks WHERE campaign_id = c.id {df_clicks}) as clicks,
                (SELECT COUNT(*) FROM leads WHERE campaign_id = c.id {df_leads}) as leads,
                (SELECT COUNT(*) FROM leads WHERE campaign_id = c.id AND status='approved' {df_leads}) as approved,
                (SELECT COALESCE(SUM(payout),0) FROM leads WHERE campaign_id = c.id AND status='approved' {df_leads}) as revenue,
                c.cpc * (SELECT COUNT(*) FROM clicks WHERE campaign_id = c.id {df_clicks}) as cost
            FROM campaigns c
            WHERE c.offer_id IS NOT NULL
        ) c ON c.offer_id = o.id
        GROUP BY o.id
    ''', dp)
    stats_raw = c.fetchall()
    conn.close()

    stats = {}
    for row in stats_raw:
        oid, clicks, leads, approved, revenue, cost = row
        stats[oid] = {
            'clicks': clicks, 'leads': leads, 'approved': approved,
            'revenue': revenue or 0.0, 'cost': cost or 0.0
        }
    for o in offers_list:
        if o[0] not in stats:
            stats[o[0]] = {'clicks':0,'leads':0,'approved':0,'revenue':0.0,'cost':0.0}

    groups_dict = {g[0]: g[1] for g in groups_list}
    if request.headers.get('HX-Request'):
        return render_partial(OFFERS_HTML, offers=offers_list, groups=groups_list, networks=networks,
                      landers=landers, stats=stats, groups_dict=groups_dict,
                      active_page='offers', AVAILABLE_TAGS=AVAILABLE_TAGS, TAG_COLOR_MAP=TAG_COLOR_MAP,
                      period=period, start=start_str, end=end_str)
    return render_template_string(OFFERS_HTML, offers=offers_list, groups=groups_list, networks=networks,
                                  landers=landers, stats=stats, groups_dict=groups_dict,
                                  active_page='offers', AVAILABLE_TAGS=AVAILABLE_TAGS, TAG_COLOR_MAP=TAG_COLOR_MAP,
                                  period=period, start=start_str, end=end_str)

@app.route('/offer/create', methods=['POST'])
@login_required
@admin_required
def create_offer():
    data = (request.form['name'].strip(), request.form.get('group_id') or None,
            request.form.get('network_id') or None, request.form.get('url','').strip(),
            float(request.form.get('payout',0)), request.form.get('country','').strip(),
            1 if request.form.get('cap_enabled') else 0, int(request.form.get('cap_clicks',0)),
            int(request.form.get('cap_conversions',0)), int(request.form.get('cap_reset_period_hours',0)),
            request.form.get('cap_reset_time_utc3','').strip(), request.form.get('reserve_offer_id') or None,
            request.form.get('default_lander_id') or None, request.form.get('tags',''))
    conn = sqlite3.connect(DB)
    try:
        conn.execute('''INSERT INTO offers (name,group_id,affiliate_network_id,url,payout,country,cap_enabled,cap_clicks,cap_conversions,cap_reset_period_hours,cap_reset_time_utc3,reserve_offer_id,default_lander_id,tags)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', data)
        conn.commit()
    except: pass
    conn.close()
    return redirect('/offers')

@app.route('/offer/edit/<int:id>', methods=['POST'])
@login_required
@admin_required
def edit_offer(id):
    data = (request.form['name'].strip(), request.form.get('group_id') or None,
            request.form.get('network_id') or None, request.form.get('url','').strip(),
            float(request.form.get('payout',0)), request.form.get('country','').strip(),
            1 if request.form.get('cap_enabled') else 0, int(request.form.get('cap_clicks',0)),
            int(request.form.get('cap_conversions',0)), int(request.form.get('cap_reset_period_hours',0)),
            request.form.get('cap_reset_time_utc3','').strip(), request.form.get('reserve_offer_id') or None,
            request.form.get('default_lander_id') or None, request.form.get('tags',''), id)
    conn = sqlite3.connect(DB)
    conn.execute('''UPDATE offers SET name=?,group_id=?,affiliate_network_id=?,url=?,payout=?,country=?,cap_enabled=?,cap_clicks=?,cap_conversions=?,cap_reset_period_hours=?,cap_reset_time_utc3=?,reserve_offer_id=?,default_lander_id=?,tags=? WHERE id=?''', data)
    conn.commit()
    conn.close()
    return redirect('/offers')

@app.route('/offers/export-csv')
@login_required
def export_offers_csv():
    period = request.args.get('period', 'all').strip()
    start_str = request.args.get('start', '').strip()
    end_str = request.args.get('end', '').strip()
    date_from, date_to = get_date_range(period, start_str, end_str)

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    if date_from and date_to:
        df_clicks = " AND timestamp BETWEEN ? AND ?"
        df_leads = " AND timestamp BETWEEN ? AND ?"
        dp = [date_from, date_to] * 5
    else:
        df_clicks = ""
        df_leads = ""
        dp = []

    c.execute(f'''
        SELECT o.id, o.name,
            COALESCE(SUM(c.clicks),0), COALESCE(SUM(c.leads),0),
            COALESCE(SUM(c.approved),0), COALESCE(SUM(c.revenue),0),
            COALESCE(SUM(c.cost),0)
        FROM offers o
        LEFT JOIN (
            SELECT offer_id,
                (SELECT COUNT(*) FROM clicks WHERE campaign_id = c.id {df_clicks}) as clicks,
                (SELECT COUNT(*) FROM leads WHERE campaign_id = c.id {df_leads}) as leads,
                (SELECT COUNT(*) FROM leads WHERE campaign_id = c.id AND status='approved' {df_leads}) as approved,
                (SELECT COALESCE(SUM(payout),0) FROM leads WHERE campaign_id = c.id AND status='approved' {df_leads}) as revenue,
                c.cpc * (SELECT COUNT(*) FROM clicks WHERE campaign_id = c.id {df_clicks}) as cost
            FROM campaigns c WHERE c.offer_id IS NOT NULL
        ) c ON c.offer_id = o.id
        WHERE o.in_trash=0
        GROUP BY o.id
    ''', dp)
    rows = c.fetchall()
    conn.close()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID','Name','Clicks','Leads','Approved','Revenue','Cost','Profit','ROI','CPC','EPC','CR'])
    for r in rows:
        oid, name, clicks, leads, approved, revenue, cost = r
        profit = revenue - cost
        roi = (profit / cost * 100) if cost > 0 else 0
        cpc_val = (cost / clicks) if clicks > 0 else 0
        epc = (revenue / clicks) if clicks > 0 else 0
        cr = (leads / clicks * 100) if clicks > 0 else 0
        cw.writerow([oid, name, clicks, leads, approved, round(revenue,2), round(cost,4),
                     round(profit,2), f"{roi:.1f}%", round(cpc_val,4), round(epc,4), f"{cr:.2f}%"])
    return Response(si.getvalue(), mimetype="text/csv",
                    headers={"Content-disposition": "attachment; filename=offers.csv"})

@app.route('/offer/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_offer(id):
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE offers SET in_trash=1, trashed_at=CURRENT_TIMESTAMP WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash('Оффер перемещён в корзину', 'warning')
    return redirect('/offers')

# ------ Источники трафика ------
@app.route('/traffic-sources')
@login_required
def traffic_sources():
    period = request.args.get('period', 'all').strip()
    start_str = request.args.get('start', '').strip()
    end_str = request.args.get('end', '').strip()
    date_from, date_to = get_date_range(period, start_str, end_str)

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    # Загружаем источники с s2s_postback_url (иначе шаблон сломается)
    c.execute('SELECT id, name, type, s2s_postback_url FROM traffic_sources ORDER BY name')
    sources = c.fetchall()

    if date_from and date_to:
        df_clicks = " AND timestamp BETWEEN ? AND ?"
        df_leads = " AND timestamp BETWEEN ? AND ?"
        dp = [date_from, date_to] * 5
    else:
        df_clicks = ""
        df_leads = ""
        dp = []

    c.execute(f'''
        SELECT 
            ts.id,
            COALESCE(SUM(c.clicks), 0) as clicks,
            COALESCE(SUM(c.leads), 0) as leads,
            COALESCE(SUM(c.approved), 0) as approved,
            COALESCE(SUM(c.revenue), 0) as revenue,
            COALESCE(SUM(c.cost), 0) as cost
        FROM traffic_sources ts
        LEFT JOIN (
            SELECT 
                traffic_source_id,
                (SELECT COUNT(*) FROM clicks WHERE campaign_id = c.id {df_clicks}) as clicks,
                (SELECT COUNT(*) FROM leads WHERE campaign_id = c.id {df_leads}) as leads,
                (SELECT COUNT(*) FROM leads WHERE campaign_id = c.id AND status='approved' {df_leads}) as approved,
                (SELECT COALESCE(SUM(payout),0) FROM leads WHERE campaign_id = c.id AND status='approved' {df_leads}) as revenue,
                c.cpc * (SELECT COUNT(*) FROM clicks WHERE campaign_id = c.id {df_clicks}) as cost
            FROM campaigns c
        ) c ON c.traffic_source_id = ts.id
        GROUP BY ts.id
    ''', dp)
    stats_raw = c.fetchall()
    conn.close()

    stats = {}
    for row in stats_raw:
        sid, clicks, leads, approved, revenue, cost = row
        stats[sid] = {
            'clicks': clicks, 'leads': leads, 'approved': approved,
            'revenue': revenue or 0.0, 'cost': cost or 0.0
        }
    for s in sources:
        if s[0] not in stats:
            stats[s[0]] = {'clicks':0,'leads':0,'approved':0,'revenue':0.0,'cost':0.0}

    # Загружаем шаблоны S2S постбеков
    s2s_templates = {}
    if os.path.exists('/opt/moroder-tracker/s2s_postbacks.json'):
        with open('/opt/moroder-tracker/s2s_postbacks.json', 'r') as f:
            try: s2s_templates = json_lib.load(f)
            except: pass

    if request.headers.get('HX-Request'):
        return render_partial(SOURCES_HTML, sources=sources, stats=stats,
                      active_page='sources',
                      period=period, start=start_str, end=end_str,
                      s2s_templates=s2s_templates, DOMAIN=DOMAIN)
    return render_template_string(SOURCES_HTML, sources=sources, stats=stats,
                                  active_page='sources',
                                  period=period, start=start_str, end=end_str,
                                  s2s_templates=s2s_templates, DOMAIN=DOMAIN)

@app.route('/traffic-source/create', methods=['POST'])
@login_required
def create_traffic_source():
    name = request.form['name'].strip()
    s2s_url = request.form.get('s2s_postback_url', '').strip()
    conn = sqlite3.connect(DB)
    try:
        conn.execute("INSERT INTO traffic_sources (name, type, s2s_postback_url) VALUES (?, 'postback', ?)",
                     (name, s2s_url))
        conn.commit()
    except:
        pass
    conn.close()
    return redirect('/traffic-sources')

@app.route('/traffic-source/edit/<int:id>', methods=['POST'])
@login_required
def edit_traffic_source(id):
    name = request.form['name'].strip()
    s2s_url = request.form.get('s2s_postback_url', '').strip()
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE traffic_sources SET name=?, s2s_postback_url=? WHERE id=?", (name, s2s_url, id))
    conn.commit()
    conn.close()
    return redirect('/traffic-sources')

@app.route('/traffic-sources/export-csv')
@login_required
def export_sources_csv():
    period = request.args.get('period', 'all').strip()
    start_str = request.args.get('start', '').strip()
    end_str = request.args.get('end', '').strip()
    date_from, date_to = get_date_range(period, start_str, end_str)

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    if date_from and date_to:
        df_clicks = " AND timestamp BETWEEN ? AND ?"
        df_leads = " AND timestamp BETWEEN ? AND ?"
        dp = [date_from, date_to] * 5
    else:
        df_clicks = ""
        df_leads = ""
        dp = []

    c.execute(f'''
        SELECT ts.id, ts.name,
            COALESCE(SUM(c.clicks),0), COALESCE(SUM(c.leads),0),
            COALESCE(SUM(c.approved),0), COALESCE(SUM(c.revenue),0),
            COALESCE(SUM(c.cost),0)
        FROM traffic_sources ts
        LEFT JOIN (
            SELECT traffic_source_id,
                (SELECT COUNT(*) FROM clicks WHERE campaign_id = c.id {df_clicks}) as clicks,
                (SELECT COUNT(*) FROM leads WHERE campaign_id = c.id {df_leads}) as leads,
                (SELECT COUNT(*) FROM leads WHERE campaign_id = c.id AND status='approved' {df_leads}) as approved,
                (SELECT COALESCE(SUM(payout),0) FROM leads WHERE campaign_id = c.id AND status='approved' {df_leads}) as revenue,
                c.cpc * (SELECT COUNT(*) FROM clicks WHERE campaign_id = c.id {df_clicks}) as cost
            FROM campaigns c
        ) c ON c.traffic_source_id = ts.id
        GROUP BY ts.id
    ''', dp)
    rows = c.fetchall()
    conn.close()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID','Name','Clicks','Leads','Approved','Revenue','Cost','Profit','ROI','CPC','EPC','CR'])
    for r in rows:
        sid, name, clicks, leads, approved, revenue, cost = r
        profit = revenue - cost
        roi = (profit / cost * 100) if cost > 0 else 0
        cpc_val = (cost / clicks) if clicks > 0 else 0
        epc = (revenue / clicks) if clicks > 0 else 0
        cr = (leads / clicks * 100) if clicks > 0 else 0
        cw.writerow([sid, name, clicks, leads, approved, round(revenue,2), round(cost,4),
                     round(profit,2), f"{roi:.1f}%", round(cpc_val,4), round(epc,4), f"{cr:.2f}%"])
    return Response(si.getvalue(), mimetype="text/csv",
                    headers={"Content-disposition": "attachment; filename=sources.csv"})

@app.route('/traffic-source/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_traffic_source(id):
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE campaigns SET traffic_source_id = NULL WHERE traffic_source_id=?", (id,))
    conn.execute("DELETE FROM traffic_sources WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect('/traffic-sources')

# ------ Партнёрские сети ------
@app.route('/affiliate-networks')
@login_required
def affiliate_networks():
    period = request.args.get('period', 'all').strip()
    start_str = request.args.get('start', '').strip()
    end_str = request.args.get('end', '').strip()
    date_from, date_to = get_date_range(period, start_str, end_str)

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT id, name FROM affiliate_networks ORDER BY name')
    networks = c.fetchall()

    if date_from and date_to:
        df_clicks = " AND timestamp BETWEEN ? AND ?"
        df_leads = " AND timestamp BETWEEN ? AND ?"
        dp = [date_from, date_to] * 5
    else:
        df_clicks = ""
        df_leads = ""
        dp = []

    c.execute(f'''
        SELECT 
            an.id,
            COALESCE(SUM(c.clicks), 0) as clicks,
            COALESCE(SUM(c.leads), 0) as leads,
            COALESCE(SUM(c.approved), 0) as approved,
            COALESCE(SUM(c.revenue), 0) as revenue,
            COALESCE(SUM(c.cost), 0) as cost
        FROM affiliate_networks an
        LEFT JOIN (
            SELECT 
                affiliate_network_id,
                (SELECT COUNT(*) FROM clicks WHERE campaign_id = c.id {df_clicks}) as clicks,
                (SELECT COUNT(*) FROM leads WHERE campaign_id = c.id {df_leads}) as leads,
                (SELECT COUNT(*) FROM leads WHERE campaign_id = c.id AND status='approved' {df_leads}) as approved,
                (SELECT COALESCE(SUM(payout),0) FROM leads WHERE campaign_id = c.id AND status='approved' {df_leads}) as revenue,
                c.cpc * (SELECT COUNT(*) FROM clicks WHERE campaign_id = c.id {df_clicks}) as cost
            FROM campaigns c
            WHERE c.affiliate_network_id IS NOT NULL
        ) c ON c.affiliate_network_id = an.id
        GROUP BY an.id
    ''', dp)
    stats_raw = c.fetchall()
    conn.close()

    stats = {}
    for row in stats_raw:
        nid, clicks, leads, approved, revenue, cost = row
        stats[nid] = {
            'clicks': clicks, 'leads': leads, 'approved': approved,
            'revenue': revenue or 0.0, 'cost': cost or 0.0
        }
    for n in networks:
        if n[0] not in stats:
            stats[n[0]] = {'clicks':0,'leads':0,'approved':0,'revenue':0.0,'cost':0.0}

    templates = {}
    if os.path.exists(TEMPLATES_FILE):
        with open(TEMPLATES_FILE,'r') as f:
            try: templates = json_lib.load(f)
            except: pass

    if request.headers.get('HX-Request'):
        return render_partial(AFFILIATE_HTML, networks=networks, stats=stats,
                              templates=templates, active_page='affiliate', DOMAIN=DOMAIN,
                              period=period, start=start_str, end=end_str)
    return render_template_string(AFFILIATE_HTML, networks=networks, stats=stats,
                                  templates=templates, active_page='affiliate', DOMAIN=DOMAIN,
                                  period=period, start=start_str, end=end_str)

@app.route('/affiliate-network/create', methods=['POST'])
@login_required
def create_affiliate_network():
    url_tmpl = request.form.get('url_template','').strip()
    postback_tmpl = request.form.get('postback_url_template','').strip()
    # Автоматически подставляем реальный домен вместо {host}
    url_tmpl = url_tmpl.replace('{host}', DOMAIN)
    postback_tmpl = postback_tmpl.replace('{host}', DOMAIN)
    conn = sqlite3.connect(DB)
    try:
        conn.execute("INSERT INTO affiliate_networks (name,url_template,postback_url_template) VALUES (?,?,?)",
                     (request.form['name'].strip(), url_tmpl, postback_tmpl))
        conn.commit()
    except: pass
    conn.close()
    return redirect('/affiliate-networks')

@app.route('/affiliate-network/edit/<int:id>', methods=['POST'])
@login_required
def edit_affiliate_network(id):
    url_tmpl = request.form.get('url_template','').strip()
    postback_tmpl = request.form.get('postback_url_template','').strip()
    url_tmpl = url_tmpl.replace('{host}', DOMAIN)
    postback_tmpl = postback_tmpl.replace('{host}', DOMAIN)
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE affiliate_networks SET name=?,url_template=?,postback_url_template=? WHERE id=?",
                 (request.form['name'].strip(), url_tmpl, postback_tmpl, id))
    conn.commit()
    conn.close()
    return redirect('/affiliate-networks')

@app.route('/affiliate-networks/export-csv')
@login_required
def export_affiliates_csv():
    period = request.args.get('period', 'all').strip()
    start_str = request.args.get('start', '').strip()
    end_str = request.args.get('end', '').strip()
    date_from, date_to = get_date_range(period, start_str, end_str)

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    if date_from and date_to:
        df_clicks = " AND timestamp BETWEEN ? AND ?"
        df_leads = " AND timestamp BETWEEN ? AND ?"
        dp = [date_from, date_to] * 5
    else:
        df_clicks = ""
        df_leads = ""
        dp = []

    c.execute(f'''
        SELECT an.id, an.name,
            COALESCE(SUM(c.clicks),0), COALESCE(SUM(c.leads),0),
            COALESCE(SUM(c.approved),0), COALESCE(SUM(c.revenue),0),
            COALESCE(SUM(c.cost),0)
        FROM affiliate_networks an
        LEFT JOIN (
            SELECT affiliate_network_id,
                (SELECT COUNT(*) FROM clicks WHERE campaign_id = c.id {df_clicks}) as clicks,
                (SELECT COUNT(*) FROM leads WHERE campaign_id = c.id {df_leads}) as leads,
                (SELECT COUNT(*) FROM leads WHERE campaign_id = c.id AND status='approved' {df_leads}) as approved,
                (SELECT COALESCE(SUM(payout),0) FROM leads WHERE campaign_id = c.id AND status='approved' {df_leads}) as revenue,
                c.cpc * (SELECT COUNT(*) FROM clicks WHERE campaign_id = c.id {df_clicks}) as cost
            FROM campaigns c WHERE c.affiliate_network_id IS NOT NULL
        ) c ON c.affiliate_network_id = an.id
        GROUP BY an.id
    ''', dp)
    rows = c.fetchall()
    conn.close()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID','Name','Clicks','Leads','Approved','Revenue','Cost','Profit','ROI','CPC','EPC','CR'])
    for r in rows:
        aid, name, clicks, leads, approved, revenue, cost = r
        profit = revenue - cost
        roi = (profit / cost * 100) if cost > 0 else 0
        cpc_val = (cost / clicks) if clicks > 0 else 0
        epc = (revenue / clicks) if clicks > 0 else 0
        cr = (leads / clicks * 100) if clicks > 0 else 0
        cw.writerow([aid, name, clicks, leads, approved, round(revenue,2), round(cost,4),
                     round(profit,2), f"{roi:.1f}%", round(cpc_val,4), round(epc,4), f"{cr:.2f}%"])
    return Response(si.getvalue(), mimetype="text/csv",
                    headers={"Content-disposition": "attachment; filename=affiliates.csv"})

@app.route('/affiliate-network/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_affiliate_network(id):
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE campaigns SET affiliate_network_id = NULL WHERE affiliate_network_id=?", (id,))
    conn.execute("DELETE FROM affiliate_networks WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect('/affiliate-networks')

# ------ Группы ------
@app.route('/groups')
@login_required
def groups():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''
        SELECT g.id, g.name,
            (SELECT COUNT(*) FROM landers WHERE group_id = g.id AND in_trash=0) as landers_count,
            (SELECT COUNT(*) FROM offers WHERE group_id = g.id AND in_trash=0) as offers_count
        FROM groups g
        ORDER BY g.name
    ''')
    groups_list = c.fetchall()
    conn.close()
    if request.headers.get('HX-Request'):
        return render_partial(GROUPS_HTML, groups=groups_list, active_page='groups')
    return render_template_string(GROUPS_HTML, groups=groups_list, active_page='groups')

@app.route('/group/create', methods=['POST'])
@login_required
def create_group():
    name = request.form['name'].strip()
    if not name:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Название обязательно'}), 400
        return redirect('/groups')
    conn = sqlite3.connect(DB)
    try:
        conn.execute("INSERT INTO groups (name) VALUES (?)", (name,))
        conn.commit()
        cur = conn.execute("SELECT id FROM groups WHERE name=?", (name,))
        group_id = cur.fetchone()[0]
        conn.close()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'id': group_id, 'name': name})
        return redirect('/groups')
    except Exception as e:
        conn.close()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Ошибка: возможно, группа уже существует'}), 400
        flash('Ошибка при создании группы', 'danger')
        return redirect('/groups')

@app.route('/group/edit/<int:id>', methods=['POST'])
@login_required
def edit_group(id):
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE groups SET name=? WHERE id=?", (request.form['name'].strip(), id))
    conn.commit()
    conn.close()
    return redirect('/groups')

@app.route('/group/delete/<int:id>', methods=['POST'])
@login_required
def delete_group(id):
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE landers SET group_id=NULL WHERE group_id=?", (id,))
    conn.execute("UPDATE offers SET group_id=NULL WHERE group_id=?", (id,))
    conn.execute("DELETE FROM groups WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect('/groups')

# ----- Восстановление и полное удаление из корзины ------
@app.route('/campaign/restore/<int:id>', methods=['POST'])
@login_required
def restore_campaign(id):
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE campaigns SET in_trash=0, trashed_at=NULL WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash('Кампания восстановлена', 'success')
    return redirect('/settings#trashTab')

@app.route('/campaign/destroy/<int:id>', methods=['POST'])
@login_required
def destroy_campaign(id):
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM clicks WHERE campaign_id=?", (id,))
    conn.execute("DELETE FROM leads WHERE campaign_id=?", (id,))
    conn.execute("DELETE FROM rules WHERE campaign_id=?", (id,))
    conn.execute("DELETE FROM campaigns WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash('Кампания удалена навсегда', 'danger')
    return redirect('/settings#trashTab')

@app.route('/lander/restore/<int:id>', methods=['POST'])
@login_required
def restore_lander(id):
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE landers SET in_trash=0, trashed_at=NULL WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash('Лендинг восстановлен', 'success')
    return redirect('/settings#trashTab')

@app.route('/lander/destroy/<int:id>', methods=['POST'])
@login_required
def destroy_lander(id):
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM landers WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash('Лендинг удалён навсегда', 'danger')
    return redirect('/settings#trashTab')

@app.route('/offer/restore/<int:id>', methods=['POST'])
@login_required
def restore_offer(id):
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE offers SET in_trash=0, trashed_at=NULL WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash('Оффер восстановлен', 'success')
    return redirect('/settings#trashTab')

@app.route('/offer/destroy/<int:id>', methods=['POST'])
@login_required
def destroy_offer(id):
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM offers WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash('Оффер удалён навсегда', 'danger')
    return redirect('/settings#trashTab')

@app.route('/settings/update_trash_days', methods=['POST'])
@login_required
def update_trash_days():
    days = request.form.get('trash_days', '7').strip()
    if not days.isdigit():
        flash('Введите число дней', 'danger')
    else:
        conn = sqlite3.connect(DB)
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('trash_days', ?)", (days,))
        conn.commit()
        conn.close()
        flash(f'Срок хранения корзины установлен: {days} дн.', 'success')
    return redirect('/settings#trashTab')

@app.route('/postback-log')
@login_required
@admin_required
def postback_log():
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * PER_PAGE
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM postback_log')
    total = c.fetchone()[0]
    c.execute('''SELECT id, timestamp, click_id, payout, status, raw_url, ip, campaign_id, offer_id
                 FROM postback_log ORDER BY timestamp DESC LIMIT ? OFFSET ?''', (PER_PAGE, offset))
    rows = c.fetchall()
    conn.close()
    total_pages = (total + PER_PAGE - 1) // PER_PAGE
    if request.args.get('embed') == '1':
        return render_template_string(POSTBACK_LOG_EMBED_HTML, rows=rows, page=page, total_pages=total_pages)
    return render_template_string(POSTBACK_LOG_HTML, rows=rows, page=page, total_pages=total_pages, active_page='settings')

@app.route('/campaigns/sub-report')
@login_required
def campaigns_sub_report():
    dim = request.args.get('dim', 'sub1')
    if dim not in ['sub1','sub2','sub3','sub4','sub5','sub6','sub7','sub8','sub9','sub10','sub11','goal']:
        return jsonify({'success': False})
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    # Берём только активные кампании, клики за всё время (можно добавить даты при желании)
    if dim == 'goal':
        c.execute('''SELECT COALESCE(l.goal,'default'), COUNT(DISTINCT cl.id) as clicks,
                     COUNT(DISTINCT l.click_id) as leads,
                     SUM(CASE WHEN l.status='approved' THEN 1 ELSE 0 END) as approved,
                     COALESCE(SUM(CASE WHEN l.status='approved' THEN l.payout ELSE 0 END),0) as revenue,
                     c.cpc * COUNT(DISTINCT cl.id) as cost
                  FROM leads l
                  JOIN clicks cl ON l.click_id = cl.click_id
                  JOIN campaigns c ON l.campaign_id = c.id
                  WHERE c.in_trash=0
                  GROUP BY l.goal''')
    else:
        col = dim
        c.execute(f'''SELECT COALESCE(cl.{col},'-'), COUNT(*) as clicks,
                     COUNT(DISTINCT l.click_id) as leads,
                     SUM(CASE WHEN l.status='approved' THEN 1 ELSE 0 END) as approved,
                     COALESCE(SUM(CASE WHEN l.status='approved' THEN l.payout ELSE 0 END),0) as revenue,
                     c.cpc * COUNT(*) as cost
                  FROM clicks cl
                  LEFT JOIN leads l ON cl.click_id = l.click_id
                  JOIN campaigns c ON cl.campaign_id = c.id
                  WHERE c.in_trash=0
                  GROUP BY cl.{col}''')
    rows = c.fetchall()
    conn.close()
    result = []
    for r in rows:
        rev = r[4] or 0
        cost = r[5] or 0
        roi = ((rev - cost) / cost * 100) if cost > 0 else 0
        result.append({
            'value': r[0],
            'clicks': r[1],
            'leads': r[2],
            'approved': r[3],
            'revenue': rev,
            'cost': cost,
            'roi': roi
        })
    return jsonify({'success': True, 'rows': result})

@app.route('/conversion-log')
@login_required
def conversion_log():
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * PER_PAGE
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    # Считаем общее количество конверсий
    c.execute('SELECT COUNT(*) FROM conversions')
    total = c.fetchone()[0]
    
    # Основной запрос: всё, что есть про каждую конверсию
    c.execute('''
        SELECT 
            conv.id,
            conv.timestamp,
            conv.click_id,
            conv.payout,
            leads.status as lead_status,
            leads.goal,
            COALESCE(c.name, '—') as campaign_name,
            COALESCE(o.name, '—') as offer_name,
            COALESCE(l.name, '—') as lander_name,
            cl.ip,
            cl.user_agent,
            cl.country,
            cl.city,
            cl.sub1, cl.sub2, cl.sub3, cl.sub4, cl.sub5,
            cl.sub6, cl.sub7, cl.sub8, cl.sub9, cl.sub10, cl.sub11,
            pl.raw_params
        FROM conversions conv
        LEFT JOIN leads ON conv.click_id = leads.click_id
        LEFT JOIN clicks cl ON conv.click_id = cl.click_id
        LEFT JOIN campaigns c ON leads.campaign_id = c.id
        LEFT JOIN offers o ON leads.offer_id = o.id
        LEFT JOIN landers l ON leads.lander_id = l.id
        LEFT JOIN postback_log pl ON conv.click_id = pl.click_id
        ORDER BY conv.timestamp DESC
        LIMIT ? OFFSET ?
    ''', (PER_PAGE, offset))
    rows = c.fetchall()
    conn.close()
    
    total_pages = (total + PER_PAGE - 1) // PER_PAGE
    if request.args.get('embed') == '1':
        return render_template_string(CONVERSION_LOG_EMBED_HTML, rows=rows, page=page, total_pages=total_pages)
    return render_template_string(CONVERSION_LOG_HTML, rows=rows, page=page, total_pages=total_pages, active_page='settings')

@app.route('/landers/bulk-action', methods=['POST'])
@login_required
def landers_bulk_action():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Неверные данные'}), 400
    action = data.get('action')
    ids = data.get('ids', [])
    if not ids or not isinstance(ids, list):
        return jsonify({'error': 'Не выбраны лендинги'}), 400

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    try:
        if action == 'trash':
            for lid in ids:
                c.execute("UPDATE landers SET in_trash=1, trashed_at=CURRENT_TIMESTAMP WHERE id=?", (lid,))
        elif action == 'restore':
            for lid in ids:
                c.execute("UPDATE landers SET in_trash=0, trashed_at=NULL WHERE id=?", (lid,))
        elif action == 'destroy':
            for lid in ids:
                # Удаляем связанные файлы, если нужно (опционально)
                c.execute("DELETE FROM landers WHERE id=?", (lid,))
        elif action == 'set_group':
            group_id = data.get('group_id')
            for lid in ids:
                c.execute("UPDATE landers SET group_id=? WHERE id=?", (group_id, lid))
        elif action == 'set_tags':
            tags = data.get('tags', '')
            tag_mode = data.get('tag_mode', 'add')
            for lid in ids:
                if tag_mode == 'replace':
                    c.execute("UPDATE landers SET tags=? WHERE id=?", (tags, lid))
                else:  # add
                    c.execute("SELECT tags FROM landers WHERE id=?", (lid,))
                    row = c.fetchone()
                    current_tags = row[0] if row else ''
                    current_list = [t.strip() for t in current_tags.split(',') if t.strip()]
                    new_list = [t.strip() for t in tags.split(',') if t.strip()]
                    merged = list(dict.fromkeys(current_list + new_list))
                    c.execute("UPDATE landers SET tags=? WHERE id=?", (','.join(merged), lid))
        else:
            conn.close()
            return jsonify({'error': 'Неизвестное действие'}), 400
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/offers/bulk-action', methods=['POST'])
@login_required
def offers_bulk_action():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Неверные данные'}), 400
    action = data.get('action')
    ids = data.get('ids', [])
    if not ids or not isinstance(ids, list):
        return jsonify({'error': 'Не выбраны офферы'}), 400

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    try:
        if action == 'trash':
            for oid in ids:
                c.execute("UPDATE offers SET in_trash=1, trashed_at=CURRENT_TIMESTAMP WHERE id=?", (oid,))
        elif action == 'restore':
            for oid in ids:
                c.execute("UPDATE offers SET in_trash=0, trashed_at=NULL WHERE id=?", (oid,))
        elif action == 'destroy':
            for oid in ids:
                c.execute("DELETE FROM offers WHERE id=?", (oid,))
        elif action == 'set_group':
            group_id = data.get('group_id')
            for oid in ids:
                c.execute("UPDATE offers SET group_id=? WHERE id=?", (group_id, oid))
        elif action == 'set_tags':
            tags = data.get('tags', '')
            tag_mode = data.get('tag_mode', 'add')
            for oid in ids:
                if tag_mode == 'replace':
                    c.execute("UPDATE offers SET tags=? WHERE id=?", (tags, oid))
                else:  # add
                    c.execute("SELECT tags FROM offers WHERE id=?", (oid,))
                    row = c.fetchone()
                    current_tags = row[0] if row else ''
                    current_list = [t.strip() for t in current_tags.split(',') if t.strip()]
                    new_list = [t.strip() for t in tags.split(',') if t.strip()]
                    merged = list(dict.fromkeys(current_list + new_list))
                    c.execute("UPDATE offers SET tags=? WHERE id=?", (','.join(merged), oid))
        else:
            conn.close()
            return jsonify({'error': 'Неизвестное действие'}), 400
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/add-manual-cost', methods=['POST'])
@login_required
def add_manual_cost():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Неверные данные'}), 400
    source_id = data.get('source_id')
    date = data.get('date')
    cost = data.get('cost')
    impressions = data.get('impressions', 0)
    clicks = data.get('clicks', 0)
    if not source_id or not date or not cost:
        return jsonify({'error': 'Заполните обязательные поля'}), 400
    try:
        cost_val = float(cost)
        imp_val = int(impressions) if impressions else 0
        click_val = int(clicks) if clicks else 0
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute('''INSERT INTO traffic_costs (traffic_source_id, date, cost, impressions, clicks, source_type)
                     VALUES (?, ?, ?, ?, ?, 'manual')''',
                  (source_id, date, cost_val, imp_val, click_val))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/get-cost-history')
@login_required
def get_cost_history():
    source_id = request.args.get('source_id', '')
    if not source_id:
        return jsonify({'error': 'source_id required'}), 400
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''SELECT date, cost, impressions, clicks, source_type
                 FROM traffic_costs
                 WHERE traffic_source_id = ?
                 ORDER BY date DESC, id DESC
                 LIMIT 50''', (source_id,))
    rows = c.fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append({
            'date': r[0],
            'cost': r[1],
            'impressions': r[2],
            'clicks': r[3],
            'source_type': r[4]
        })
    return jsonify({'success': True, 'rows': result})

@app.route('/dashboard')
@login_required
def dashboard():
    if request.headers.get('HX-Request'):
        return render_partial(DASHBOARD_HTML, active_page='dashboard')
    return render_template_string(DASHBOARD_HTML, active_page='dashboard')

@app.route('/dashboard/data')
@login_required
def dashboard_data():
    period = request.args.get('period', 'all').strip()
    start_str = request.args.get('start', '').strip()
    end_str = request.args.get('end', '').strip()
    date_from, date_to = get_date_range(period, start_str, end_str)

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    if date_from and date_to:
        d_clicks = " AND timestamp BETWEEN ? AND ?"
        d_leads = " AND timestamp BETWEEN ? AND ?"
        dp_summary = [date_from, date_to] * 5
        dp_chart = [date_from, date_to] * 4
    else:
        d_clicks = ""
        d_leads = ""
        dp_summary = []
        dp_chart = []

    # Сводные метрики
    c.execute(f'''
        SELECT 
            (SELECT COUNT(*) FROM clicks WHERE 1=1 {d_clicks}) as clicks,
            (SELECT COUNT(*) FROM leads WHERE 1=1 {d_leads}) as leads,
            (SELECT COUNT(*) FROM leads WHERE status='approved' {d_leads}) as approved,
            (SELECT COALESCE(SUM(payout),0) FROM leads WHERE status='approved' {d_leads}) as revenue,
            (SELECT COALESCE(SUM(c.cpc * (SELECT COUNT(*) FROM clicks WHERE campaign_id = c.id {d_clicks})),0) FROM campaigns c) as cost
    ''', dp_summary)
    summary = c.fetchone()
    clicks, leads, approved, revenue, cost = summary

    # Данные по дням
    c.execute(f'''
        SELECT DATE(cl.timestamp) as day,
               COUNT(*) as clicks,
               (SELECT COUNT(*) FROM leads l WHERE DATE(l.timestamp) = DATE(cl.timestamp) {d_leads}) as leads,
               (SELECT COALESCE(SUM(l2.payout),0) FROM leads l2 WHERE l2.status='approved' AND DATE(l2.timestamp) = DATE(cl.timestamp) {d_leads}) as revenue,
               (SELECT COALESCE(SUM(c.cpc),0) FROM campaigns c JOIN clicks cl2 ON cl2.campaign_id = c.id WHERE DATE(cl2.timestamp) = DATE(cl.timestamp) {d_clicks}) as cost
        FROM clicks cl
        WHERE 1=1 {d_clicks}
        GROUP BY DATE(cl.timestamp)
        ORDER BY DATE(cl.timestamp)
    ''', dp_chart)
    rows = c.fetchall()
    conn.close()

    labels = []
    revenue_series = []
    cost_series = []
    for r in rows:
        labels.append(r[0])
        revenue_series.append(round(r[3] or 0, 2))
        cost_series.append(round(r[4] or 0, 4))

    return jsonify({
        'summary': {
            'clicks': clicks,
            'leads': leads,
            'approved': approved,
            'revenue': round(revenue or 0, 2),
            'cost': round(cost or 0, 4),
            'profit': round(revenue - cost, 2),
            'roi': round(((revenue - cost) / cost * 100) if cost > 0 else 0, 1)
        },
        'chart': {
            'labels': labels,
            'revenue': revenue_series,
            'cost': cost_series
        }
    })

@app.route('/get-reset-items')
@login_required
@admin_required
def get_reset_items():
    entity_type = request.args.get('type', 'campaigns')
    table_map = {
        'campaigns': 'campaigns',
        'landers': 'landers',
        'offers': 'offers',
        'traffic-sources': 'traffic_sources',
        'affiliate-networks': 'affiliate_networks'
    }
    table = table_map.get(entity_type)
    if not table:
        return jsonify({'items': []})
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(f"SELECT id, name FROM {table} ORDER BY name")
    items = [{'id': row[0], 'name': row[1]} for row in c.fetchall()]
    conn.close()
    return jsonify({'items': items})

@app.route('/reset-stats', methods=['POST'])
@login_required
@admin_required
def reset_stats():
    data = request.get_json()
    entity_type = data.get('type')
    item_id = data.get('item_id', 'all')

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    try:
        if entity_type == 'campaigns':
            if item_id == 'all':
                c.execute("DELETE FROM clicks")
                c.execute("DELETE FROM leads")
                c.execute("DELETE FROM conversions")
                c.execute("DELETE FROM postback_log")
            else:
                c.execute("DELETE FROM clicks WHERE campaign_id=?", (item_id,))
                c.execute("DELETE FROM leads WHERE campaign_id=?", (item_id,))
                c.execute("DELETE FROM conversions WHERE click_id IN (SELECT click_id FROM clicks WHERE campaign_id=?)", (item_id,))
                c.execute("DELETE FROM postback_log WHERE campaign_id=?", (item_id,))
        elif entity_type == 'landers':
            if item_id == 'all':
                c.execute("DELETE FROM clicks WHERE lander_id IS NOT NULL")
                c.execute("DELETE FROM leads WHERE lander_id IS NOT NULL")
            else:
                c.execute("DELETE FROM clicks WHERE lander_id=?", (item_id,))
                c.execute("DELETE FROM leads WHERE lander_id=?", (item_id,))
        elif entity_type == 'offers':
            if item_id == 'all':
                c.execute("DELETE FROM clicks WHERE offer_id IS NOT NULL")
                c.execute("DELETE FROM leads WHERE offer_id IS NOT NULL")
            else:
                c.execute("DELETE FROM clicks WHERE offer_id=?", (item_id,))
                c.execute("DELETE FROM leads WHERE offer_id=?", (item_id,))
        elif entity_type == 'traffic_sources':
            if item_id == 'all':
                c.execute("DELETE FROM clicks WHERE campaign_id IN (SELECT id FROM campaigns WHERE traffic_source_id IS NOT NULL)")
                c.execute("DELETE FROM leads WHERE campaign_id IN (SELECT id FROM campaigns WHERE traffic_source_id IS NOT NULL)")
            else:
                c.execute("DELETE FROM clicks WHERE campaign_id IN (SELECT id FROM campaigns WHERE traffic_source_id=?)", (item_id,))
                c.execute("DELETE FROM leads WHERE campaign_id IN (SELECT id FROM campaigns WHERE traffic_source_id=?)", (item_id,))
        elif entity_type == 'affiliate_networks':
            if item_id == 'all':
                c.execute("DELETE FROM clicks WHERE campaign_id IN (SELECT id FROM campaigns WHERE affiliate_network_id IS NOT NULL)")
                c.execute("DELETE FROM leads WHERE campaign_id IN (SELECT id FROM campaigns WHERE affiliate_network_id IS NOT NULL)")
            else:
                c.execute("DELETE FROM clicks WHERE campaign_id IN (SELECT id FROM campaigns WHERE affiliate_network_id=?)", (item_id,))
                c.execute("DELETE FROM leads WHERE campaign_id IN (SELECT id FROM campaigns WHERE affiliate_network_id=?)", (item_id,))
        else:
            conn.close()
            return jsonify({'error': 'Неизвестный тип'})
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)})

@app.route('/admin/user/generate-api-key/<int:id>', methods=['POST'])
@login_required
@admin_required
def generate_api_key(id):
    new_key = secrets.token_hex(16)
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE users SET api_key=? WHERE id=?", (new_key, id))
    conn.commit()
    conn.close()
    flash(f'Новый API-ключ для пользователя: {new_key}', 'success')
    return redirect('/settings')

@app.route('/api/groups', methods=['GET','POST'])
@api_login_required
def api_groups():
    if request.method == 'GET':
        conn = sqlite3.connect(DB); c = conn.cursor()
        c.execute("SELECT id, name FROM groups ORDER BY name")
        rows = c.fetchall()
        conn.close()
        return jsonify({'success':True, 'data': [dict(zip(['id','name'], r)) for r in rows]})

    data = request.get_json()
    name = data.get('name','').strip()
    if not name: return jsonify({'error':'Name required'}), 400
    conn = sqlite3.connect(DB)
    try:
        conn.execute("INSERT INTO groups (name) VALUES (?)", (name,))
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit(); conn.close()
        return jsonify({'success':True, 'id':new_id})
    except Exception as e:
        conn.close(); return jsonify({'error':str(e)}), 500

@app.route('/api/groups/<int:id>', methods=['GET','PUT','DELETE'])
@api_login_required
def api_group(id):
    if request.method == 'GET':
        conn = sqlite3.connect(DB); c = conn.cursor()
        c.execute("SELECT * FROM groups WHERE id=?", (id,))
        row = c.fetchone()
        conn.close()
        if not row: return jsonify({'error':'Not found'}), 404
        cols = [desc[0] for desc in c.description]
        return jsonify({'success':True, 'data': dict(zip(cols, row))})

    if request.method == 'PUT':
        data = request.get_json()
        if 'name' not in data: return jsonify({'error':'Name required'}), 400
        conn = sqlite3.connect(DB)
        conn.execute("UPDATE groups SET name=? WHERE id=?", (data['name'].strip(), id))
        conn.commit(); conn.close()
        return jsonify({'success':True})

    if request.method == 'DELETE':
        conn = sqlite3.connect(DB)
        conn.execute("UPDATE landers SET group_id=NULL WHERE group_id=?", (id,))
        conn.execute("UPDATE offers SET group_id=NULL WHERE group_id=?", (id,))
        conn.execute("DELETE FROM groups WHERE id=?", (id,))
        conn.commit(); conn.close()
        return jsonify({'success':True})

@app.route('/api/traffic_costs', methods=['GET','POST'])
@api_login_required
def api_traffic_costs():
    if request.method == 'GET':
        source_id = request.args.get('source_id')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        query = "SELECT id, traffic_source_id, date, cost, impressions, clicks, source_type FROM traffic_costs WHERE 1=1"
        params = []
        if source_id:
            query += " AND traffic_source_id=?"; params.append(source_id)
        if date_from:
            query += " AND date >= ?"; params.append(date_from)
        if date_to:
            query += " AND date <= ?"; params.append(date_to)
        query += " ORDER BY date DESC LIMIT 100"
        conn = sqlite3.connect(DB); c = conn.cursor()
        c.execute(query, params)
        rows = c.fetchall()
        conn.close()
        return jsonify({'success':True, 'data': [dict(zip(['id','traffic_source_id','date','cost','impressions','clicks','source_type'], r)) for r in rows]})

    # POST – добавление ручного расхода
    data = request.get_json()
    src = data.get('traffic_source_id')
    date = data.get('date')
    cost = data.get('cost')
    if not src or not date or cost is None: return jsonify({'error':'source_id, date, cost required'}), 400
    try:
        cost = float(cost)
        imp = int(data.get('impressions',0))
        clk = int(data.get('clicks',0))
        conn = sqlite3.connect(DB)
        conn.execute("INSERT INTO traffic_costs (traffic_source_id, date, cost, impressions, clicks, source_type) VALUES (?,?,?,?,?,'manual')",
                     (src, date, cost, imp, clk))
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit(); conn.close()
        return jsonify({'success':True, 'id':new_id})
    except Exception as e:
        return jsonify({'error':str(e)}), 400

@app.route('/verify-challenge', methods=['POST'])
def verify_challenge():
    click_id = request.form.get('click_id')
    lander_url = request.form.get('lander_url')
    answer = request.form.get('answer')
    expected = request.form.get('expected')
    if answer == expected:
        return redirect(f"{lander_url}?click_id={click_id}", 302)
    return "Challenge failed", 403

@app.route('/api/botlist', methods=['GET','PUT','DELETE'])
@api_login_required
@admin_required
def api_botlist():
    if request.method == 'GET':
        conn = sqlite3.connect(DB); c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='global_ip_blacklist'")
        black = c.fetchone()
        c.execute("SELECT value FROM settings WHERE key='global_ip_whitelist'")
        white = c.fetchone()
        conn.close()
        return jsonify({'success':True, 'blacklist': black[0] if black else '', 'whitelist': white[0] if white else ''})

    if request.method == 'PUT':
        data = request.get_json()
        black = data.get('blacklist','')
        white = data.get('whitelist','')
        conn = sqlite3.connect(DB)
        conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES ('global_ip_blacklist',?)", (black,))
        conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES ('global_ip_whitelist',?)", (white,))
        conn.commit(); conn.close()
        return jsonify({'success':True})

    if request.method == 'DELETE':
        conn = sqlite3.connect(DB)
        conn.execute("DELETE FROM settings WHERE key IN ('global_ip_blacklist','global_ip_whitelist')")
        conn.commit(); conn.close()
        return jsonify({'success':True})

@app.route('/api/botlist/add', methods=['POST'])
@api_login_required
@admin_required
def api_botlist_add():
    data = request.get_json()
    ip = data.get('ip','').strip()
    if not ip: return jsonify({'error':'ip required'}), 400
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='global_ip_blacklist'")
    row = c.fetchone()
    current = row[0] if row else ''
    current = current.split(',') if current else []
    current = [x.strip() for x in current if x.strip()]
    if ip not in current:
        current.append(ip)
        conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES ('global_ip_blacklist',?)", (','.join(current),))
    conn.commit(); conn.close()
    return jsonify({'success':True})

@app.route('/api/botlist/exclude', methods=['POST'])
@api_login_required
@admin_required
def api_botlist_exclude():
    data = request.get_json()
    ip = data.get('ip','').strip()
    if not ip: return jsonify({'error':'ip required'}), 400
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='global_ip_blacklist'")
    row = c.fetchone()
    if row and row[0]:
        current = [x.strip() for x in row[0].split(',') if x.strip()]
        if ip in current:
            current.remove(ip)
            conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES ('global_ip_blacklist',?)", (','.join(current),))
    conn.commit(); conn.close()
    return jsonify({'success':True})

@app.route('/api/campaigns/<int:id>/stats')
@api_login_required
def api_campaign_stats(id):
    period = request.args.get('period', 'all')
    start = request.args.get('start')
    end = request.args.get('end')
    date_from, date_to = get_date_range(period, start, end)

    conn = sqlite3.connect(DB); c = conn.cursor()
    if date_from and date_to:
        df_clicks = " AND timestamp BETWEEN ? AND ?"
        df_leads = " AND timestamp BETWEEN ? AND ?"
        dp = [date_from, date_to] * 5
    else:
        df_clicks = df_leads = ""
        dp = []

    c.execute(f'''
        SELECT 
            (SELECT COUNT(*) FROM clicks WHERE campaign_id=c.id {df_clicks}) clicks,
            (SELECT COUNT(*) FROM leads WHERE campaign_id=c.id {df_leads}) leads,
            (SELECT COUNT(*) FROM leads WHERE campaign_id=c.id AND status='approved' {df_leads}) approved,
            (SELECT COALESCE(SUM(payout),0) FROM leads WHERE campaign_id=c.id AND status='approved' {df_leads}) revenue,
            (SELECT COALESCE(MAX(api_spent), c.cpc * (SELECT COUNT(*) FROM clicks WHERE campaign_id=c.id {df_clicks})) FROM campaigns WHERE id=c.id) cost
        FROM campaigns c WHERE c.id=?
    ''', dp + [id])
    stats = c.fetchone()
    conn.close()
    if not stats: return jsonify({'error':'Campaign not found'}), 404
    clicks, leads, approved, revenue, cost = stats
    profit = revenue - cost
    roi = (profit / cost * 100) if cost > 0 else 0
    return jsonify({'success':True, 'data': {
        'clicks': clicks, 'leads': leads, 'approved': approved,
        'revenue': round(revenue,2), 'cost': round(cost,4),
        'profit': round(profit,2), 'roi': round(roi,1)
    }})

@app.route('/api/conversions/log', methods=['GET'])
@api_login_required
def api_conversions_log():
    campaign_id = request.args.get('campaign_id')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    limit = request.args.get('limit', 100, type=int)

    query = '''
        SELECT 
            conv.id,
            conv.timestamp,
            conv.click_id,
            conv.payout,
            leads.status as lead_status,
            leads.goal,
            COALESCE(c.name, '—') as campaign_name,
            COALESCE(o.name, '—') as offer_name,
            COALESCE(l.name, '—') as lander_name,
            cl.ip,
            cl.country,
            cl.city,
            cl.sub1, cl.sub2, cl.sub3, cl.sub4, cl.sub5,
            cl.sub6, cl.sub7, cl.sub8, cl.sub9, cl.sub10, cl.sub11,
            pl.raw_params
        FROM conversions conv
        LEFT JOIN leads ON conv.click_id = leads.click_id
        LEFT JOIN clicks cl ON conv.click_id = cl.click_id
        LEFT JOIN campaigns c ON leads.campaign_id = c.id
        LEFT JOIN offers o ON leads.offer_id = o.id
        LEFT JOIN landers l ON leads.lander_id = l.id
        LEFT JOIN postback_log pl ON conv.click_id = pl.click_id
        WHERE 1=1
    '''
    params = []
    if campaign_id:
        query += " AND c.id = ?"
        params.append(campaign_id)
    if date_from:
        query += " AND conv.timestamp >= ?"
        params.append(date_from)
    if date_to:
        query += " AND conv.timestamp <= ?"
        params.append(date_to)
    query += " ORDER BY conv.timestamp DESC LIMIT ?"
    params.append(limit)

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    cols = ['id', 'timestamp', 'click_id', 'payout', 'status', 'goal',
            'campaign_name', 'offer_name', 'lander_name', 'ip', 'country', 'city',
            'sub1', 'sub2', 'sub3', 'sub4', 'sub5', 'sub6', 'sub7', 'sub8', 'sub9', 'sub10', 'sub11',
            'raw_params']
    data = [dict(zip(cols, r)) for r in rows]
    return jsonify({'success': True, 'data': data})

@app.route('/api/clicks/log', methods=['GET'])
@api_login_required
def api_clicks_log():
    campaign_id = request.args.get('campaign_id')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    limit = request.args.get('limit', 100, type=int)
    query = "SELECT id, campaign_id, click_id, ip, country, city, timestamp, external_click_id, sub1, sub2, sub3, sub4, sub5, sub6, sub7, sub8, sub9, sub10, sub11 FROM clicks WHERE 1=1"
    params = []
    if campaign_id:
        query += " AND campaign_id=?"; params.append(campaign_id)
    if date_from:
        query += " AND timestamp >= ?"; params.append(date_from)
    if date_to:
        query += " AND timestamp <= ?"; params.append(date_to)
    query += " ORDER BY timestamp DESC LIMIT ?"; params.append(limit)
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    cols = ['id','campaign_id','click_id','ip','country','city','timestamp','external_click_id','sub1','sub2','sub3','sub4','sub5','sub6','sub7','sub8','sub9','sub10','sub11']
    return jsonify({'success':True, 'data': [dict(zip(cols, r)) for r in rows]})

@app.route('/api/traffic_sources/<int:id>/clone', methods=['POST'])
@api_login_required
def api_traffic_source_clone(id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT * FROM traffic_sources WHERE id=?", (id,))
    orig = c.fetchone()
    if not orig:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    cols = [d[0] for d in c.description]
    data = dict(zip(cols, orig))
    data.pop('id')
    data['name'] = data['name'] + ' (копия)'
    try:
        c.execute(f"INSERT INTO traffic_sources ({','.join(data.keys())}) VALUES ({','.join(['?']*len(data))})", list(data.values()))
        new_id = c.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': new_id})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500


@app.route('/api/traffic_sources/clean_archive', methods=['POST'])
@api_login_required
def api_traffic_sources_clean_archive():
    # У источников нет архива, можно удалить все неиспользуемые или просто заглушку
    return jsonify({'success': True, 'message': 'No archive for traffic sources'})

@app.route('/api/affiliate_networks/<int:id>/clone', methods=['POST'])
@api_login_required
def api_affiliate_network_clone(id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT * FROM affiliate_networks WHERE id=?", (id,))
    orig = c.fetchone()
    if not orig:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    cols = [d[0] for d in c.description]
    data = dict(zip(cols, orig))
    data.pop('id')
    data['name'] = data['name'] + ' (копия)'
    try:
        c.execute(f"INSERT INTO affiliate_networks ({','.join(data.keys())}) VALUES ({','.join(['?']*len(data))})", list(data.values()))
        new_id = c.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': new_id})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500


@app.route('/api/affiliate_networks/clean_archive', methods=['POST'])
@api_login_required
def api_affiliate_networks_clean_archive():
    # У сетей тоже нет архива – просто заглушка
    return jsonify({'success': True, 'message': 'No archive for affiliate networks'})



# ------------------------------------------------------------
# HTML ШАБЛОНЫ
# ------------------------------------------------------------
# ------------------------------------------------------------
# ПОЛНЫЙ КОМПЛЕКТ HTML-ШАБЛОНОВ (старые + новые)
# ------------------------------------------------------------
HEADER = '''
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Мародёр Трекер</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link rel="icon" type="image/png" href="data:image/png;base64,''' + LOGO_BASE64 + '''">
  <script src="https://unpkg.com/htmx.org@1.9.10"></script>
  <style>
    body { background-color: #1a1a2e; color: #e0e0e0; font-size: 0.9rem; }
    .navbar { background: linear-gradient(135deg, #0f3460 0%, #16213e 100%); border-bottom: 2px solid #e2a03f; box-shadow: 0 2px 10px rgba(0,0,0,0.5); padding: 0.2rem 1rem; }
    .navbar-brand { font-family: 'Georgia', serif; font-size: 1.3rem; font-weight: bold; color: #e2a03f !important; text-shadow: 2px 2px 4px #000000; display: flex; align-items: center; gap: 8px; padding: 0; white-space: nowrap; }
    .navbar-brand img { height: 32px; width: 32px; border-radius: 50%; border: 2px solid #e2a03f; box-shadow: 0 0 6px #e2a03f; }
    .navbar-nav { flex-wrap: wrap; }
    .navbar-nav .nav-link { color: #c0c0c0 !important; font-weight: 500; font-size: 0.8rem; padding: 4px 6px !important; margin: 2px; border-radius: 4px; transition: all 0.2s; white-space: nowrap; }
    .navbar-nav .nav-link:hover { color: #fff !important; background-color: rgba(226, 160, 63, 0.2); }
    .navbar-text { font-size: 0.8rem; margin-right: 0.5rem !important; white-space: nowrap; }
    .btn-outline-light { border-color: #e2a03f; color: #e2a03f; font-size: 0.8rem; padding: 2px 8px; transition: 0.2s; white-space: nowrap; }
    .btn-outline-light:hover { background-color: #e2a03f; color: #000; }
    .container-fluid { padding-top: 10px; }
    .table { background-color: #16213e; color: #e0e0e0; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.4); font-size: 0.85rem; }
    .table thead { background-color: #0f3460; }
    .table th { color: #e2a03f; font-weight: bold; border-bottom: 1px solid #e2a03f; }
    .table td, .table th { border-color: #2a2a4a; padding: 0.4rem; }
    .table-hover tbody tr:hover { background-color: rgba(226, 160, 63, 0.08); }
    .btn { font-size: 0.8rem; padding: 3px 8px; border-radius: 4px; }
    .btn-sm { font-size: 0.7rem; padding: 2px 6px; }

    /* Лоадер */
    #loader-bar {
      position: fixed; top: 0; left: 0; width: 100%; height: 3px; z-index: 9999;
      background: transparent; opacity: 0; transition: opacity 0.2s;
      pointer-events: none;
    }
    #loader-bar .progress-bar-fill {
      height: 100%; width: 0%;
      background: linear-gradient(90deg, #e2a03f, #ffcc00);
      box-shadow: 0 0 10px rgba(226, 160, 63, 0.7);
      transition: width 0.3s ease-out;
    }
    /* Когда htmx в процессе запроса, показываем лоадер */
    .htmx-request #loader-bar {
      opacity: 1;
    }
    .htmx-request #loader-bar .progress-bar-fill {
      width: 100% !important;
    }

    .fade-in {
      opacity: 0; animation: fadeIn ease 0.5s forwards;
    }
    @keyframes fadeIn {
      0% { opacity: 0; transform: translateY(8px); }
      100% { opacity: 1; transform: translateY(0); }
    }

    a:active { transform: scale(0.97); transition: transform 0.1s; }
    
    .card.bg-dark, .card.bg-dark .card-header, .card.bg-dark .card-body,
    .country-dropdown, .country-dropdown .form-check-label {
        color: #e0e0e0 !important;
    }
    .country-dropdown .form-check-label { color: #e0e0e0 !important; }

    .btn-primary { background-color: #e2a03f !important; border-color: #e2a03f !important; color: #000 !important; }
    .btn-success { background-color: #2ecc71 !important; border-color: #2ecc71 !important; color: #fff !important; }
    .btn-secondary { background-color: #95a5a6 !important; border-color: #95a5a6 !important; color: #fff !important; }
    
    .modal.show .fade-in { animation: none; opacity: 1; }
    .modal-content { background-color: #1a1a2e; color: #e0e0e0; }
    .modal-header { border-bottom: 1px solid #2a2a4a; }
    .modal-footer { border-top: 1px solid #2a2a4a; }
    .tag-picker .selected-tags { min-height: 28px; }
    .tag-picker .selected-tags .badge { cursor: pointer; }
    .tag-create-btn { cursor: pointer; color: #e2a03f; }
    .modal .btn-close { filter: invert(1); }
  </style>
</head>
<script>
(function() {
  window.AVAILABLE_TAGS = {{ AVAILABLE_TAGS|tojson|safe if AVAILABLE_TAGS is defined else '[]' }};
  window.TAG_COLOR_MAP = {{ TAG_COLOR_MAP|tojson|safe if TAG_COLOR_MAP is defined else '{}' }};

  function initTagPickers() {
    document.querySelectorAll('.tag-picker').forEach(picker => {
      if (picker.dataset.initialized) return;
      picker.dataset.initialized = '1';

      const searchInput = picker.querySelector('.tag-search');
      const dropdown = picker.querySelector('.tag-dropdown');
      const hiddenInput = picker.querySelector('input[name="tags"]');
      const selectedContainer = picker.querySelector('.selected-tags');
      const createBtn = picker.querySelector('.tag-create-btn');

      let allTags = [...window.AVAILABLE_TAGS];

      function updateView() {
        const checked = [];
        selectedContainer.innerHTML = '';
        picker.querySelectorAll('.tag-check:checked').forEach(cb => {
          checked.push(cb.value);
          const color = cb.dataset.color || '#95a5a6';
          const badge = document.createElement('span');
          badge.className = 'badge me-1 mb-1';
          badge.style.backgroundColor = color;
          badge.style.cursor = 'pointer';
          badge.textContent = cb.value + ' ✕';
          badge.onclick = () => { cb.checked = false; updateView(); };
          selectedContainer.appendChild(badge);
        });
        hiddenInput.value = checked.join(',');
      }

      function addTagToDropdown(tag, color) {
        const exist = picker.querySelector(`.tag-check[value="${tag}"]`);
        if (exist) return;
        const div = document.createElement('div');
        div.className = 'form-check';
        div.innerHTML = `
          <input class="form-check-input tag-check" type="checkbox" value="${tag}" data-color="${color}" id="tag_${tag}_${picker.dataset.name || 'default'}">
          <label class="form-check-label" for="tag_${tag}_${picker.dataset.name || 'default'}">
            <span class="badge" style="background-color:${color};margin-right:5px;">&nbsp;</span> ${tag}
          </label>`;
        div.querySelector('.tag-check').addEventListener('change', updateView);
        dropdown.appendChild(div);
        allTags.push(tag);
      }

      picker.querySelectorAll('.tag-check').forEach(cb => {
        cb.addEventListener('change', updateView);
        const label = cb.parentNode.querySelector('label .badge');
        if (label) cb.dataset.color = label.style.backgroundColor || '#95a5a6';
      });

      const initial = hiddenInput.value || '';
      const selected = initial ? initial.split(',').map(s => s.trim()) : [];
      picker.querySelectorAll('.tag-check').forEach(cb => { cb.checked = selected.includes(cb.value); });
      updateView();

      searchInput.addEventListener('input', () => {
        const filter = searchInput.value.toUpperCase();
        picker.querySelectorAll('.form-check').forEach(item => {
          const label = item.querySelector('label');
          item.style.display = label && label.textContent.toUpperCase().includes(filter) ? '' : 'none';
        });
      });

      searchInput.addEventListener('focus', () => dropdown.style.display = 'block');
      searchInput.addEventListener('blur', () => { setTimeout(() => dropdown.style.display = 'none', 200); });

      if (createBtn) {
        createBtn.addEventListener('click', () => {
          const newTag = searchInput.value.trim();
          if (!newTag) return;
          if (allTags.includes(newTag)) { alert('Такой тег уже есть'); return; }
          const customColor = '#95a5a6';
          addTagToDropdown(newTag, customColor);
          const newCb = picker.querySelector(`.tag-check[value="${newTag}"]`);
          if (newCb) { newCb.checked = true; updateView(); }
          searchInput.value = '';
        });
      }
    });
  }

  document.addEventListener('DOMContentLoaded', initTagPickers);
})();
</script>
<body>
  <div id="loader-bar"><div class="progress-bar-fill"></div></div>

<nav class="navbar navbar-expand-lg navbar-dark">
  <div class="container-fluid">
    <a class="navbar-brand" href="/campaigns">
      <img src="data:image/png;base64,''' + LOGO_BASE64 + '''" alt="Jolly Roger">
      Мародёр
    </a>
    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
      <span class="navbar-toggler-icon"></span>
    </button>
    <div class="collapse navbar-collapse" id="navbarNav">
      <ul class="navbar-nav me-auto">
        <li class="nav-item"><a class="nav-link" href="/dashboard" hx-get="/dashboard" hx-target="#main-content" hx-push-url="true">📊 Дашборд</a></li>
        <li class="nav-item"><a class="nav-link" href="/campaigns" hx-get="/campaigns" hx-target="#main-content" hx-push-url="true">Кампании</a></li>
        <li class="nav-item"><a class="nav-link" href="/clicklog" hx-get="/clicklog" hx-target="#main-content" hx-push-url="true">Клик-лог</a></li>
        <li class="nav-item"><a class="nav-link" href="/traffic-sources" hx-get="/traffic-sources" hx-target="#main-content" hx-push-url="true">Источники</a></li>
        <li class="nav-item"><a class="nav-link" href="/affiliate-networks" hx-get="/affiliate-networks" hx-target="#main-content" hx-push-url="true">Партнёрки</a></li>
        <li class="nav-item"><a class="nav-link" href="/landers" hx-get="/landers" hx-target="#main-content" hx-push-url="true">Лендинги</a></li>
        <li class="nav-item"><a class="nav-link" href="/offers" hx-get="/offers" hx-target="#main-content" hx-push-url="true">Офферы</a></li>
        <li class="nav-item"><a class="nav-link" href="/groups" hx-get="/groups" hx-target="#main-content" hx-push-url="true">Группы</a></li>
        <li class="nav-item"><a class="nav-link" href="/manual-ops" hx-get="/manual-ops" hx-target="#main-content" hx-push-url="true">Ручные</a></li>
        <li class="nav-item"><a class="nav-link" href="/settings" hx-get="/settings" hx-target="#main-content" hx-push-url="true">Настройки</a></li>
      </ul>
      <span class="navbar-text me-3">
        {{ session.username }} ({{ session.role }})
      </span>
      <a class="btn btn-outline-light btn-sm" href="/login">Выход</a>
    </div>
  </div>
</nav>
<div class="container-fluid">
  {% with messages = get_flashed_messages(with_categories=true) %}
  {% if messages %}
    {% for category, message in messages %}
      <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
        {{ message }}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
    {% endfor %}
  {% endif %}
  {% endwith %}
  <!-- BEGIN MAIN CONTENT -->
  <div id="main-content" hx-history-elt>
'''

# ВНИМАНИЕ: Не забудь добавить скрипт для прогресс-бара в самый конец твоего FOOTER!
# Сейчас FOOTER заканчивается на </script></body></html>''', а должен быть таким:

FOOTER = '''</div><!-- конец #main-content -->
<!-- END MAIN CONTENT -->
<hr>
<div id="tg-banner" class="text-center mb-3"><small>
  <img src="data:image/png;base64,''' + FAVICON_BASE64 + '''" style="height:16px; vertical-align:middle; margin-right:4px;">
  🔥 Подпишись на Telegram-канал разработчика: <a href="https://t.me/moraderweb" target="_blank" style="color: #ff4444; font-weight: bold;">@moraderweb</a> — там анонсы, обновления и полезные плюшки для арбитража.
  <button onclick="document.getElementById('tg-banner').style.display='none'" style="background:none;border:none;color:#aaa;cursor:pointer;font-size:1.2em;">&times;</button>
</small></div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://unpkg.com/htmx.org@1.9.10"></script>
<script>
// === HTMX глобальные события ===
// === HTMX анимация загрузки ===
document.body.addEventListener('htmx:beforeSend', function() {
  var bar = document.getElementById('loader-bar');
  if(bar) bar.style.opacity = '1';
});

document.body.addEventListener('htmx:afterSettle', function() {
  var bar = document.getElementById('loader-bar');
  if(bar) bar.style.opacity = '0';

  // Анимация появления нового контента
  var main = document.getElementById('main-content');
  if (main) {
    main.classList.add('fade-in');
    setTimeout(() => main.classList.remove('fade-in'), 500);
  }

  // Переинициализация tag-пикеров
  if (typeof initTagPickers === 'function') {
    initTagPickers();
  }

  // Переинициализация country-пикеров
  document.querySelectorAll('.country-picker').forEach(picker => {
    const searchInput = picker.querySelector('.country-search');
    const dropdown = picker.querySelector('.country-dropdown');
    const checkboxes = picker.querySelectorAll('.country-check');
    const hiddenSelect = picker.querySelector('select[multiple]');
    const selectedContainer = picker.querySelector('.selected-countries');

    function updateHiddenSelect() {
      while (hiddenSelect.options.length > 0) hiddenSelect.remove(0);
      selectedContainer.innerHTML = '';
      checkboxes.forEach(cb => {
        if (cb.checked) {
          const opt = document.createElement('option');
          opt.value = cb.value;
          opt.selected = true;
          hiddenSelect.appendChild(opt);
          const badge = document.createElement('span');
          badge.className = 'badge bg-warning text-dark me-1 mb-1';
          badge.innerHTML = cb.value + ' ✕';
          badge.style.cursor = 'pointer';
          badge.onclick = function() {
            cb.checked = false;
            updateHiddenSelect();
          };
          selectedContainer.appendChild(badge);
        }
      });
    }

    const selectedData = picker.getAttribute('data-selected');
    if (selectedData) {
      try {
        const selectedCodes = JSON.parse(selectedData);
        checkboxes.forEach(cb => { cb.checked = selectedCodes.includes(cb.value); });
        updateHiddenSelect();
      } catch(e) {}
    } else {
      updateHiddenSelect();
    }

    searchInput.addEventListener('input', function() {
      const filter = this.value.toUpperCase();
      checkboxes.forEach(cb => {
        const label = cb.parentNode.querySelector('label').textContent.toUpperCase();
        cb.parentNode.style.display = label.includes(filter) ? '' : 'none';
      });
    }); // <-- закрыли обработчик input

    searchInput.addEventListener('focus', function() { dropdown.style.display = 'block'; });
    searchInput.addEventListener('blur', function() {
      setTimeout(() => dropdown.style.display = 'none', 200);
    });

    checkboxes.forEach(cb => { cb.addEventListener('change', updateHiddenSelect); });
  }); // <-- закрыли forEach для country-picker

  // Автоматически открываем модалку, если она появилась в #modal-container
  var modalContainer = document.getElementById('modal-container');
  if (modalContainer) {
    var modalElement = modalContainer.querySelector('.modal');
    if (modalElement) {
      var modalInstance = new bootstrap.Modal(modalElement);
      modalInstance.show();
    }

    // Инициализация правил для редактирования
    modalContainer.querySelectorAll('.cloak-rule-row').forEach(row => {
      const selectType = row.querySelector('[name^="rule_condition_type_"]');
      if (selectType) {
        const idx = selectType.name.match(/\d+/)[0];
        const selectedValue = row.getAttribute('data-rule-value') || '';
        updateRuleValueControl(selectType, idx, selectedValue);
      }
    });
    // Обновляем сумму процентов
    if (typeof updateSum === 'function') updateSum();
  }

  // Подсветка активного пункта меню
  const currentPath = window.location.pathname;
  document.querySelectorAll('.navbar-nav .nav-link').forEach(link => {
    link.classList.remove('active');
    if (link.getAttribute('href') === currentPath) {
      link.classList.add('active');
    }
  });
});

// ===== Универсальные функции для путей и правил =====
function addPath() {
    const container = document.getElementById('pathsContainer');
    if (!container) return;
    const idx = container.querySelectorAll('.path-row').length;
    const div = document.createElement('div');
    div.className = 'row mb-2 align-items-center path-row';
    div.innerHTML = `
      <div class="col-md-3">
        <select class="form-select form-select-sm" name="path_lander_${idx}">
          <option value="">-- Лендинг --</option>
          ${(window.landers || []).map(l => `<option value="${l[0]}">${l[1]}</option>`).join('')}
        </select>
      </div>
      <div class="col-md-3">
        <select class="form-select form-select-sm" name="path_offer_${idx}">
          <option value="">-- Оффер --</option>
          ${(window.offers || []).map(o => `<option value="${o[0]}">${o[1]}</option>`).join('')}
        </select>
      </div>
      <div class="col-md-2">
        <input type="number" class="form-control form-control-sm" name="path_percent_${idx}" value="0" min="0" max="100" oninput="updateSum()">
      </div>
      <div class="col-md-2">
        <button type="button" class="btn btn-sm btn-outline-danger" onclick="this.closest('.path-row').remove(); updateSum()">✕</button>
      </div>
    `;
    container.appendChild(div);
    updateSum();
}

function updateSum() {
    const paths = document.querySelectorAll('[name^="path_percent_"]');
    let sum = 0;
    paths.forEach(inp => sum += parseInt(inp.value) || 0);
    const sumEl = document.getElementById('percentSum');
    if (sumEl) sumEl.textContent = sum;
}

function addCloakRule() {
    const container = document.getElementById('cloakRulesContainer');
    if (!container) return;
    const idx = container.querySelectorAll('.cloak-rule-row').length;
    const div = document.createElement('div');
    div.className = 'row mb-2 align-items-center cloak-rule-row';
    div.innerHTML = `
      <div class="col-md-2">
        <select class="form-select form-select-sm" name="rule_condition_type_${idx}" onchange="updateRuleValueControl(this, ${idx})">
          <option value="country">Страна</option>
          <option value="device">Устройство</option>
          <option value="os">ОС</option>
          <option value="browser">Браузер</option>
          <option value="bot_keywords">Боты</option>
        </select>
      </div>
      <div class="col-md-1">
        <select class="form-select form-select-sm" name="rule_operator_${idx}">
          <option value="equals">Равно</option>
          <option value="not_equals">Не равно</option>
        </select>
      </div>
      <div class="col-md-2" id="rule_value_container_${idx}"></div>
      <div class="col-md-2">
        <select class="form-select form-select-sm" name="rule_action_${idx}">
          <option value="allow_path">Показать путь</option>
          <option value="block">Заблокировать</option>
          <option value="allow_default">По умолчанию</option>
        </select>
      </div>
      <div class="col-md-2">
        <select class="form-select form-select-sm" name="rule_lander_${idx}">
          <option value="">-- Лендинг --</option>
          ${(window.landers || []).map(l => `<option value="${l[0]}">${l[1]}</option>`).join('')}
        </select>
      </div>
      <div class="col-md-2">
        <select class="form-select form-select-sm" name="rule_offer_${idx}">
          <option value="">-- Оффер --</option>
          ${(window.offers || []).map(o => `<option value="${o[0]}">${o[1]}</option>`).join('')}
        </select>
      </div>
      <div class="col-md-1">
        <input class="form-check-input" type="checkbox" name="rule_js_${idx}">
      </div>
      <div class="col-md-1">
        <button type="button" class="btn btn-sm btn-outline-danger" onclick="this.closest('.cloak-rule-row').remove()">✕</button>
      </div>
    `;
    container.appendChild(div);
    updateRuleValueControl(div.querySelector('select[name="rule_condition_type_' + idx + '"]'), idx);
}

// Без этой функции будет ошибка при смене типа правила
function updateRuleValueControl(selectEl, idx, selectedValue = '') {
    const condType = selectEl.value;
    const container = document.getElementById('rule_value_container_' + idx);
    if (!container) return;
    let options = '';
    if (condType === 'country') {
        options = '<option value="">-- Выберите страну --</option>';
        for (const [code, name] of Object.entries(window.COUNTRY_CODES || {})) {
            const selected = (code === selectedValue) ? ' selected' : '';
            options += `<option value="${code}"${selected}>${name} (${code})</option>`;
        }
        container.innerHTML = `<select class="form-select form-select-sm" name="rule_value_${idx}">${options}</select>`;
    } else if (condType === 'device') {
        const devices = ['desktop','mobile','tablet'];
        options = devices.map(d => `<option value="${d}"${d === selectedValue ? ' selected' : ''}>${d}</option>`).join('');
        container.innerHTML = `<select class="form-select form-select-sm" name="rule_value_${idx}">${options}</select>`;
    } else if (condType === 'os') {
        const oss = ['Windows','Android','iOS','Linux','Mac OS X'];
        options = oss.map(o => `<option value="${o}"${o === selectedValue ? ' selected' : ''}>${o}</option>`).join('');
        container.innerHTML = `<select class="form-select form-select-sm" name="rule_value_${idx}">${options}</select>`;
    } else if (condType === 'browser') {
        const browsers = ['Chrome','Firefox','Safari','Edge','Opera'];
        options = browsers.map(b => `<option value="${b}"${b === selectedValue ? ' selected' : ''}>${b}</option>`).join('');
        container.innerHTML = `<select class="form-select form-select-sm" name="rule_value_${idx}">${options}</select>`;
    } else if (condType === 'bot_keywords') {
        // Для простоты текстовое поле, но можно добавить select с ботами
        container.innerHTML = `<input type="text" class="form-control form-control-sm" name="rule_value_${idx}" value="${selectedValue}">`;
    } else {
        container.innerHTML = `<input type="text" class="form-control form-control-sm" name="rule_value_${idx}" value="${selectedValue}">`;
    }
}

// Создание группы (быстрая функция)
async function createGroup(selectElement) {
  const name = prompt('Название новой группы:');
  if (!name) return;
  const resp = await fetch('/group/create', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'X-Requested-With': 'XMLHttpRequest'
    },
    body: 'name=' + encodeURIComponent(name.trim())
  });
  const data = await resp.json();
  if (data.error) {
    alert(data.error);
  } else {
    const option = new Option(data.name, data.id, true, true);
    selectElement.appendChild(option);
    selectElement.value = data.id;
  }
}
</script>
</body>
</html>'''

SETTINGS_HTML = HEADER + '''
<h4>⚙️ Настройки</h4>
<ul class="nav nav-tabs mb-3">
  <li class="nav-item"><a class="nav-link active" data-bs-toggle="tab" href="#domainsTab">🏴‍☠️ Домены</a></li>
  <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#serverTab">🖥️ Сервер</a></li>
  {% if session.role == 'admin' %}
  <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#usersTab">👥 Пользователи</a></li>
  {% endif %}
  <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#docsTab">📄 Документация</a></li>
  <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#resetStatsTab">🔄 Сброс статистики</a></li>
  <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#trashTab">🗑️ Корзина</a></li>
  <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#postbackLogTab">📡 Лог постбеков</a></li>
  <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#conversionLogTab">📋 Лог конверсий</a></li>
  <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#globalIpTab">🌐 Глобальные IP</a></li>
</ul>
<div class="tab-content">
  <div class="tab-pane fade show active" id="domainsTab">
    <h5>Управление доменами</h5>
    <table class="table table-striped table-hover">
      <thead><tr><th>Домен</th><th>SSL</th><th>По умолчанию</th><th>Действия</th></tr></thead>
      <tbody>
      {% for d in domains %}
      <tr>
        <td>{{ d[1] }}</td>
        <td>{{ d[3] }}</td>
        <td>{{ 'Да' if d[2] == 1 else 'Нет' }}</td>
        <td>
          {% if d[2] != 1 %}<form method="post" action="/domain/set_default/{{ d[0] }}" style="display:inline"><button class="btn btn-sm btn-outline-primary">Сделать основным</button></form>{% endif %}
          <form method="post" action="/domain/delete/{{ d[0] }}" style="display:inline"><button class="btn btn-sm btn-danger">Удалить</button></form>
        </td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
    <form class="row g-3 mt-3" method="post" action="/domain/add">
      <div class="col-auto"><input class="form-control" name="domain" placeholder="new-domain.com" required></div>
      <div class="col-auto"><button class="btn btn-primary">Добавить домен</button></div>
    </form>
  </div>

  <div class="tab-pane fade" id="resetStatsTab">
    <h5>Сброс статистики</h5>
    <div class="row g-3">
      <div class="col-auto">
        <select class="form-select form-select-sm" id="resetType" onchange="loadResetItems()">
          <option value="campaigns">Кампании</option>
          <option value="landers">Лендинги</option>
          <option value="offers">Офферы</option>
          <option value="traffic_sources">Источники</option>
          <option value="affiliate_networks">Партнёрки</option>
        </select>
      </div>
      <div class="col-auto">
        <select class="form-select form-select-sm" id="resetItem">
          <option value="all">Все</option>
        </select>
      </div>
      <div class="col-auto">
        <button class="btn btn-sm btn-danger" onclick="resetStats()">Удалить</button>
      </div>
    </div>
  </div>

  <div class="tab-pane fade" id="postbackLogTab">
    <iframe src="/postback-log?embed=1" style="width:100%;height:600px;border:none;"></iframe>
  </div>

  <div class="tab-pane fade" id="conversionLogTab">
    <iframe src="/conversion-log?embed=1" style="width:100%;height:600px;border:none;"></iframe>
  </div>

  <div class="tab-pane fade" id="trashTab">
    <h5>Корзина</h5>
    <form method="post" action="/settings/update_trash_days" class="row g-3 mb-3">
      <div class="col-auto">
        <label>Автоудаление через (дней):</label>
        <input type="number" class="form-control form-control-sm" name="trash_days" value="{{ trash_days }}" min="0" style="width:100px">
      </div>
      <div class="col-auto align-self-end">
        <button class="btn btn-sm btn-primary">Сохранить</button>
      </div>
    </form>
    {% if trashed_items %}
    <table class="table table-striped table-hover">
      <thead><tr><th>ID</th><th>Название</th><th>Тип</th><th>Удалено</th><th>Действия</th></tr></thead>
      <tbody>
      {% for item in trashed_items %}
      <tr>
        <td>{{ item[0] }}</td>
        <td>{{ item[1] }}</td>
        <td>{{ item[2] }}</td>
        <td>{{ item[4] or '—' }}</td>
        <td>
          {% if item[2] == 'campaign' %}
            <form method="post" action="/campaign/restore/{{ item[0] }}" style="display:inline"><button class="btn btn-sm btn-success">↩️</button></form>
            <form method="post" action="/campaign/destroy/{{ item[0] }}" style="display:inline"><button class="btn btn-sm btn-danger">🗑️</button></form>
          {% elif item[2] == 'lander' %}
            <form method="post" action="/lander/restore/{{ item[0] }}" style="display:inline"><button class="btn btn-sm btn-success">↩️</button></form>
            <form method="post" action="/lander/destroy/{{ item[0] }}" style="display:inline"><button class="btn btn-sm btn-danger">🗑️</button></form>
          {% elif item[2] == 'offer' %}
            <form method="post" action="/offer/restore/{{ item[0] }}" style="display:inline"><button class="btn btn-sm btn-success">↩️</button></form>
            <form method="post" action="/offer/destroy/{{ item[0] }}" style="display:inline"><button class="btn btn-sm btn-danger">🗑️</button></form>
          {% endif %}
        </td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
    {% else %}
    <p class="text-muted">Корзина пуста.</p>
    {% endif %}
  </div>

  <div class="tab-pane fade" id="serverTab">
    <h5>Состояние сервера</h5>
    <table class="table table-striped"><tbody>
      <tr><td>CPU</td><td>{{ cpu }}%</td></tr>
      <tr><td>RAM</td><td>{{ mem.used // 1024**2 }} MB / {{ mem.total // 1024**2 }} MB ({{ mem.percent }}%)</td></tr>
      <tr><td>Диск</td><td>{{ disk.used // 1024**3 }} GB / {{ disk.total // 1024**3 }} GB ({{ disk.percent }}%)</td></tr>
      <tr><td>Нагрузка</td><td>{{ "%.2f %.2f %.2f"|format(load[0], load[1], load[2]) }}</td></tr>
      <tr><td>Аптайм</td><td>{{ uptime_str }}</td></tr>
    </tbody></table>
    <p>IP сервера: <code>{{ local_ip }}</code></p>
  </div>

  {% if session.role == 'admin' %}
  <div class="tab-pane fade" id="usersTab">
    <h5>Пользователи <button class="btn btn-primary btn-sm float-end" data-bs-toggle="modal" data-bs-target="#createUserModal">Создать</button></h5>
    <table class="table table-striped table-hover">
      <thead><tr><th>ID</th><th>Логин</th><th>Роль</th><th>API-ключ</th><th></th></tr></thead>
      <tbody>
      {% for u in users %}
      <tr>
        <td>{{u[0]}}</td><td>{{u[1]}}</td><td>{{u[2]}}</td>
        <td><code>{{ u[3] if u[3] else '—' }}</code></td>
        <td>
          <button class="btn btn-sm btn-warning" data-bs-toggle="modal" data-bs-target="#editUserModal{{u[0]}}">✎</button>
          <form method="post" action="/admin/user/delete/{{u[0]}}" style="display:inline"><button class="btn btn-sm btn-danger">🗑</button></form>
          <form method="post" action="/admin/user/generate-api-key/{{u[0]}}" style="display:inline"><button class="btn btn-sm btn-outline-info">🔑</button></form>
        </td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
    {% for u in users %}
    <div class="modal fade" id="editUserModal{{u[0]}}" tabindex="-1"><div class="modal-dialog"><form class="modal-content" method="post" action="/admin/user/edit/{{u[0]}}"><div class="modal-header"><h5>Редактировать пользователя</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div><div class="modal-body">
    <label>Логин</label><input class="form-control" name="username" value="{{u[1]}}" required>
    <label>Новый пароль</label><input class="form-control" name="password" type="password" placeholder="Оставьте пустым">
    <label>Роль</label><select class="form-select" name="role"><option value="admin" {{'selected' if u[2]=='admin'}}>Админ</option><option value="manager" {{'selected' if u[2]=='manager'}}>Менеджер</option><option value="guest" {{'selected' if u[2]=='guest'}}>Гость</option></select>
    </div><div class="modal-footer"><button class="btn btn-primary">Сохранить</button></div></form></div></div>
    {% endfor %}
    <div class="modal fade" id="createUserModal" tabindex="-1"><div class="modal-dialog"><form class="modal-content" method="post" action="/admin/user/create"><div class="modal-header"><h5>Новый пользователь</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div><div class="modal-body">
    <label>Логин</label><input class="form-control" name="username" required><label>Пароль</label><input class="form-control" name="password" type="password" required>
    <label>Роль</label><select class="form-select" name="role"><option value="admin">Админ</option><option value="manager">Менеджер</option><option value="guest">Гость</option></select>
    </div><div class="modal-footer"><button class="btn btn-primary">Создать</button></div></form></div></div>
  </div>
  {% endif %}

  <div class="tab-pane fade" id="docsTab">
    <h5>Документация</h5>
    <pre style="background: #16213e; color: #e0e0e0; padding: 15px; border-radius: 8px; white-space: pre-wrap;">{{ doc_content or 'Документация не найдена. Создайте файл /opt/moroder-tracker/doc.txt' }}</pre>
  </div>

  <!-- ========== ГЛОБАЛЬНЫЕ СПИСКИ IP ========== -->
  <div class="tab-pane fade" id="globalIpTab">
    <h5>Глобальные списки IP (применяются ко всем кампаниям)</h5>
    <form method="post">
      <div class="mb-3">
        <label class="form-label">Чёрный список IP</label>
        <textarea class="form-control" name="ip_blacklist" rows="4" placeholder="IP через запятую">{{ global_ip_blacklist }}</textarea>
      </div>
      <div class="mb-3">
        <label class="form-label">Белый список IP</label>
        <textarea class="form-control" name="ip_whitelist" rows="4" placeholder="IP через запятую (если задан, только эти IP будут пропущены)">{{ global_ip_whitelist }}</textarea>
      </div>
      <button type="submit" class="btn btn-primary">Сохранить</button>
    </form>
  </div>
</div>

<script>
async function loadResetItems() {
  const type = document.getElementById('resetType').value;
  const select = document.getElementById('resetItem');
  select.innerHTML = '<option value="all">Все</option>';
  let apiType = type;
  if (type === 'traffic_sources') apiType = 'traffic-sources';
  if (type === 'affiliate_networks') apiType = 'affiliate-networks';
  const resp = await fetch('/get-reset-items?type=' + apiType);
  const data = await resp.json();
  data.items.forEach(item => {
    const option = new Option(item.name, item.id);
    select.appendChild(option);
  });
}

async function resetStats() {
  if (!confirm('Удалить ВСЮ статистику для выбранных? Это необратимо!')) return;
  const type = document.getElementById('resetType').value;
  const itemId = document.getElementById('resetItem').value;
  const resp = await fetch('/reset-stats', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ type, item_id: itemId })
  });
  const result = await resp.json();
  alert(result.success ? 'Статистика удалена' : 'Ошибка: ' + result.error);
}

document.addEventListener('DOMContentLoaded', loadResetItems);
</script>
''' + FOOTER

LOGIN_HTML = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Marauder Tracker - Вход</title>
    <style>
        :root {
            --bg: #0d0d0d;
            --panel: #1a1a1a;
            --gold: #c9a227;
            --gold-hover: #e0b84a;
            --text: #eaeaea;
            --error: #ff4d4d;
            --input-bg: #2a2a2a;
            --input-border: #444;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: var(--bg);
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            color: var(--text);
        }
        .login-container {
            background: var(--panel);
            border: 1px solid #333;
            border-radius: 16px;
            padding: 40px;
            width: 100%;
            max-width: 420px;
            box-shadow: 0 0 30px rgba(201, 162, 39, 0.1);
            animation: fadeIn 0.5s ease;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .login-container h2 {
            font-size: 2rem;
            margin-bottom: 10px;
            color: var(--gold);
            font-weight: 700;
            letter-spacing: 1px;
            text-align: center;
        }
        .login-container .subtitle {
            text-align: center;
            margin-bottom: 30px;
            color: #aaa;
            font-size: 0.9rem;
        }
        .form-group {
            margin-bottom: 20px;
        }
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-size: 0.9rem;
            color: #ccc;
        }
        .form-group input {
            width: 100%;
            padding: 12px 15px;
            background: var(--input-bg);
            border: 1px solid var(--input-border);
            border-radius: 8px;
            color: #fff;
            font-size: 1rem;
            transition: border 0.3s;
        }
        .form-group input:focus {
            outline: none;
            border-color: var(--gold);
        }
        .btn-login {
            width: 100%;
            padding: 14px;
            background: var(--gold);
            border: none;
            border-radius: 8px;
            color: #0d0d0d;
            font-size: 1.1rem;
            font-weight: bold;
            cursor: pointer;
            transition: background 0.3s;
            letter-spacing: 0.5px;
        }
        .btn-login:hover {
            background: var(--gold-hover);
        }
        .error-message {
            background: rgba(255, 77, 77, 0.1);
            border: 1px solid var(--error);
            color: var(--error);
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 0.9rem;
            text-align: center;
        }
        .blocked-info {
            color: #ffa500;
            text-align: center;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <h2>MARAUDER</h2>
        <div class="subtitle">Вход в систему управления</div>
        {% if error %}
            <div class="error-message">{{ error }}</div>
        {% endif %}
        {% if blocked %}
            <div class="blocked-info">Вход временно заблокирован. Подождите указанное время.</div>
        {% endif %}
        <form method="post">
            <div class="form-group">
                <label for="username">Логин</label>
                <input type="text" id="username" name="username" required autofocus>
            </div>
            <div class="form-group">
                <label for="password">Пароль</label>
                <input type="password" id="password" name="password" required>
            </div>
            <button type="submit" class="btn-login">Войти</button>
        </form>
    </div>
</body>
</html>
'''

CONVERSION_LOG_HTML = HEADER + '''
<h4>📋 Лог конверсий</h4>
<table class="table table-sm table-hover">
<thead>
  <tr>
    <th>ID</th>
    <th>Время</th>
    <th>Click ID</th>
    <th>Выплата</th>
    <th>Статус</th>
    <th>Кампания</th>
    <th>Оффер</th>
    <th>Лендинг</th>
    <th>IP</th>
    <th>User-Agent</th>
    <th>Страна</th>
    <th>Город</th>
    <th>Параметры</th>
  </tr>
</thead>
<tbody>
{% for r in rows %}
<tr>
  <td>{{ r[0] }}</td>
  <td>{{ r[1] }}</td>
  <td><code>{{ r[2] }}</code></td>
  <td>${{ "%.2f"|format(r[3]) }}</td>
  <td>{{ r[4] or '-' }}</td>
  <td>{{ r[5] }}</td>
  <td>{{ r[6] }}</td>
  <td>{{ r[7] }}</td>
  <td>{{ r[8] or '-' }}</td>
  <td style="max-width:150px;overflow:hidden;text-overflow:ellipsis;">{{ r[9] or '-' }}</td>
  <td>{{ r[10] or '-' }}</td>
  <td>{{ r[11] or '-' }}</td>
  <td>
    {% if r[12] %}
      <button class="btn btn-sm btn-outline-info" onclick="showConvParams('{{ r[0] }}')">👁️</button>
      <pre id="conv-params-{{ r[0] }}" style="display:none;">{{ r[12] }}</pre>
    {% else %}
      —
    {% endif %}
  </td>
</tr>
{% endfor %}
</tbody>
</table>
<nav><ul class="pagination">{% for p in range(1,total_pages+1) %}<li class="page-item {{'active' if p==page}}"><a class="page-link" href="?page={{p}}">{{p}}</a></li>{% endfor %}</ul></nav>

<!-- Модалка для параметров -->
<div class="modal fade" id="convParamsModal" tabindex="-1">
  <div class="modal-dialog modal-lg">
    <div class="modal-content bg-dark text-light">
      <div class="modal-header">
        <h5>Параметры конверсии</h5>
        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        <pre id="convParamsContent" style="white-space:pre-wrap;word-break:break-all;"></pre>
      </div>
    </div>
  </div>
</div>

<script>
function showConvParams(rowId) {
  const raw = document.getElementById('conv-params-' + rowId).textContent;
  try {
    const obj = JSON.parse(raw);
    document.getElementById('convParamsContent').textContent = JSON.stringify(obj, null, 2);
  } catch(e) {
    document.getElementById('convParamsContent').textContent = raw;
  }
  new bootstrap.Modal(document.getElementById('convParamsModal')).show();
}
</script>
''' + FOOTER

MANUAL_OPS_HTML = HEADER + '''<h4>Ручные операции</h4><div class="row"><div class="col-md-6">
<h5>Добавить конверсию</h5><form method="post" action="/manual-ops/add-conversion">
<label>Кампания</label><select class="form-select" name="campaign_id" required><option value="">--</option>{% for c in campaigns %}<option value="{{c[0]}}">{{c[1]}}</option>{% endfor %}</select>
<label>Выплата $</label><input class="form-control" name="payout" value="0" step="0.01" required>
<button class="btn btn-success mt-2">Добавить</button></form></div><div class="col-md-6">
<h5>Добавить расход</h5><form method="post" action="/manual-ops/add-spent">
<label>Кампания</label><select class="form-select" name="campaign_id" required><option value="">--</option>{% for c in campaigns %}<option value="{{c[0]}}">{{c[1]}}</option>{% endfor %}</select>
<label>Сумма $</label><input class="form-control" name="amount" value="0" step="0.01" required>
<button class="btn btn-warning mt-2">Добавить</button></form></div></div>''' + FOOTER

POSTBACK_LOG_HTML = HEADER + '''
<h4>📡 Лог постбеков</h4>
<table class="table table-sm table-hover">
<thead>
  <tr>
    <th>ID</th>
    <th>Время</th>
    <th>Click ID</th>
    <th>Выплата</th>
    <th>Статус</th>
    <th>URL</th>
    <th>IP</th>
    <th>Кампания</th>
    <th>Оффер</th>
  </tr>
</thead>
<tbody>
{% for r in rows %}
<tr>
  <td>{{ r[0] }}</td>
  <td>{{ r[1] }}</td>
  <td><code>{{ r[2] }}</code></td>
  <td>${{ "%.2f"|format(r[3]) }}</td>
  <td>{{ r[4] }}</td>
  <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;">{{ r[5] }}</td>
  <td>{{ r[6] }}</td>
  <td>{{ r[7] or '-' }}</td>
  <td>{{ r[8] or '-' }}</td>
</tr>
{% endfor %}
</tbody>
</table>
<nav><ul class="pagination">{% for p in range(1,total_pages+1) %}<li class="page-item {{'active' if p==page}}"><a class="page-link" href="?page={{p}}">{{p}}</a></li>{% endfor %}</ul></nav>
''' + FOOTER

CAMPAIGNS_HTML = HEADER + '''
<h4>Кампании <a href="/campaign/new" class="btn btn-primary btn-sm float-end">Создать</a></h4>

<div id="bulk-actions" class="mb-3 p-2 bg-dark rounded" style="display:none;">
  <span class="text-warning me-2">Выбрано: <strong id="selected-count">0</strong></span>
  <button class="btn btn-sm btn-outline-warning" onclick="bulkAction('campaigns', 'trash')">🗑️ В корзину</button>
  <button class="btn btn-sm btn-outline-warning" onclick="bulkAction('campaigns', 'set_group_prompt')">📁 Группа</button>
  <button class="btn btn-sm btn-outline-warning" onclick="bulkAction('campaigns', 'set_tags_prompt')">🏷️ Теги</button>
  <button class="btn btn-sm btn-outline-danger" onclick="clearBulkSelection()">✕ Сбросить</button>
</div>
<!-- Панель периода и экспорта -->
<form class="row g-2 mb-3" method="get" id="periodForm">
  <input type="hidden" name="tags" value="{{ filter_tags }}">
  <input type="hidden" name="country" value="{{ filter_country }}">
  <div class="col-auto">
    <select class="form-select form-select-sm" name="period" onchange="handlePeriodChange(this.value)">
      <option value="all" {{ 'selected' if period=='all' else '' }}>Всё время</option>
      <option value="today" {{ 'selected' if period=='today' else '' }}>Сегодня</option>
      <option value="yesterday" {{ 'selected' if period=='yesterday' else '' }}>Вчера</option>
      <option value="3days" {{ 'selected' if period=='3days' else '' }}>3 дня</option>
      <option value="week" {{ 'selected' if period=='week' else '' }}>Неделя</option>
      <option value="2weeks" {{ 'selected' if period=='2weeks' else '' }}>2 недели</option>
      <option value="month" {{ 'selected' if period=='month' else '' }}>Месяц</option>
      <option value="year" {{ 'selected' if period=='year' else '' }}>Год</option>
      <option value="custom" {{ 'selected' if period=='custom' else '' }}>Произвольный</option>
    </select>
  </div>
  <div class="col-auto" id="customDateFields" style="display: {{ 'block' if period=='custom' else 'none' }};">
    <input type="date" class="form-control form-control-sm d-inline w-auto" name="start" value="{{ start }}">
    <span class="text-light">—</span>
    <input type="date" class="form-control form-control-sm d-inline w-auto" name="end" value="{{ end }}">
  </div>
  <div class="col-auto">
    <button type="submit" class="btn btn-sm btn-outline-warning">Применить</button>
    <a href="/campaigns/export-csv?{{ request.query_string.decode() }}" class="btn btn-sm btn-info">📥 CSV</a>
    <button type="button" class="btn btn-sm btn-outline-warning" onclick="openSubReport()">📊 Sub-отчёт</button>
  </div>
</form>

<script>
function handlePeriodChange(val) {
  const customFields = document.getElementById('customDateFields');
  customFields.style.display = val === 'custom' ? 'block' : 'none';
  if (val !== 'custom') {
    document.getElementById('periodForm').submit();
  }
}
</script>
<form class="row g-2 mb-3" method="get">
  <div class="col-auto">
    <input class="form-control form-control-sm" name="tags" placeholder="Фильтр по тегам" value="{{ filter_tags }}">
  </div>
  <div class="col-auto">
    <select class="form-select form-select-sm" name="country">
      <option value="">Все страны</option>
      {% for code, name in COUNTRY_CODES.items() %}
      <option value="{{ code }}" {{ 'selected' if filter_country == code else '' }}>{{ name }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="col-auto"><button class="btn btn-sm btn-outline-warning">Фильтр</button></div>
</form>

<div class="table-responsive">
<table class="table table-striped table-hover" id="campaigns-table">
<thead>
  <tr>
    <th><input type="checkbox" id="select-all" onchange="toggleAll(this)"></th>
    <th>ID</th><th>Название</th><th>Группа</th><th>Теги</th><th>Страны</th>
    <th>Клики</th><th>Лиды</th><th>Аппрув</th><th>Аппрув-рейт</th>
    <th>Доход</th><th>Расход</th><th>Прибыль</th><th>ROI</th>
    <th>CPC</th><th>EPC</th><th>CR</th><th></th>
  </tr>
</thead>
<tbody>
{% for c in camps %}
  {% set clicks = c[16] %}
  {% set leads = c[17] %}
  {% set approved = c[18] %}
  {% set revenue = c[19] %}
  {% set cost = c[20] %}
  <tr>
    <td><input type="checkbox" class="bulk-check" value="{{ c[0] }}" onchange="updateBulkPanel()"></td>
    <td>{{c[0]}}</td><td>{{c[1]}}</td>
    <td>{{ groups_dict.get(c[10], '—') if groups_dict is defined else '—' }}</td>
    <td>
      {% for t in c[11].split(',') if t.strip() %}
        {% set color = TAG_COLOR_MAP.get(t.strip(), '#95a5a6') %}
        <span class="badge" style="background-color:{{color}}">{{t.strip()}}</span>
      {% endfor %}
    </td>
    <td>
      {% set country_list = c[12] %}
      {% for code in country_list %}
        {{ COUNTRY_CODES.get(code, code) }}{% if not loop.last %}, {% endif %}
      {% endfor %}
    </td>
    <td>{{clicks}}</td>
    <td>{{leads}}</td>
    <td>{{ approved }}</td>
    <td>{{ "%.1f"|format((approved/leads*100) if leads>0 else 0) }}%</td>
    <td>${{"%.2f"|format(revenue)}}</td>
    <td>${{"%.4f"|format(cost)}}</td>
    {% set profit = revenue - cost %}
    <td>${{"%.2f"|format(profit)}}</td>
    <td>{{"%.1f"|format((profit/cost*100) if cost>0 else 0)}}%</td>
    <td>${{"%.4f"|format((cost/clicks) if clicks>0 else 0)}}</td>
    <td>${{"%.4f"|format((revenue/clicks) if clicks>0 else 0)}}</td>
    <td>{{"%.2f"|format((leads/clicks*100) if clicks>0 else 0)}}%</td>
    <td>
      <button class="btn btn-sm btn-warning" 
              hx-get="/campaign/edit/{{c[0]}}/form" 
              hx-target="#modal-container" 
              hx-swap="innerHTML" 
              data-bs-toggle="modal" 
              data-bs-target="#editCampaignModal">✎</button>
      <form method="post" action="/campaign/delete/{{c[0]}}" style="display:inline"><button class="btn btn-sm btn-danger">🗑</button></form>
      <button class="btn btn-sm btn-info" onclick="loadLinks({{c[0]}})">🔗</button>
    </td>
  </tr>
{% endfor %}</tbody></table>
</div>
<nav><ul class="pagination">{% for p in range(1,total_pages+1) %}<li class="page-item {{'active' if p==page}}"><a class="page-link" href="?page={{p}}">{{p}}</a></li>{% endfor %}</ul></nav>

<!-- Контейнер для модального окна -->
<div id="modal-container"></div>

<!-- Модалка для ссылок -->
<div class="modal fade" id="linksModal" tabindex="-1">
  <div class="modal-dialog modal-lg">
    <div class="modal-content bg-dark text-light">
      <div class="modal-header">
        <h5>Ссылки для залива</h5>
        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body" id="linksContent">Загрузка...</div>
    </div>
  </div>
</div>

<!-- Модалка для Sub-отчёта -->
<div class="modal fade" id="subReportModal" tabindex="-1">
  <div class="modal-dialog modal-xl">
    <div class="modal-content bg-dark text-light">
      <div class="modal-header">
        <h5>📊 Sub-отчёт</h5>
        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        <div class="row mb-3">
          <div class="col-auto">
            <label class="form-label">Измерение</label>
            <select class="form-select form-select-sm" id="subReportDim" onchange="loadSubReport()">
              <option value="sub1">Sub 1</option>
              <option value="sub2">Sub 2</option>
              <option value="sub3">Sub 3</option>
              <option value="sub4">Sub 4</option>
              <option value="sub5">Sub 5</option>
              <option value="sub6">Sub 6</option>
              <option value="sub7">Sub 7</option>
              <option value="sub8">Sub 8</option>
              <option value="sub9">Sub 9</option>
              <option value="sub10">Sub 10</option>
              <option value="sub11">Sub 11</option>
              <option value="goal">Goal</option>
            </select>
          </div>
        </div>
        <div class="table-responsive">
          <table class="table table-sm table-striped table-hover" id="subReportTable">
            <thead>
              <tr>
                <th>Значение</th>
                <th>Клики</th>
                <th>Лиды</th>
                <th>Аппрув</th>
                <th>Доход</th>
                <th>Расход</th>
                <th>ROI</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Модалка для массового выбора группы -->
<div class="modal fade" id="bulkGroupModal" tabindex="-1">
  <div class="modal-dialog"><div class="modal-content bg-dark text-light">
    <div class="modal-header"><h5>Назначить группу</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div>
    <div class="modal-body">
      <div class="input-group input-group-sm">
        <select class="form-select" id="bulk_group_select">
          <option value="">-- Без группы --</option>
          {% for g in groups %}
          <option value="{{ g[0] }}">{{ g[1] }}</option>
          {% endfor %}
        </select>
      </div>
    </div>
    <div class="modal-footer">
      <button type="button" class="btn btn-primary" onclick="executeBulkGroup()">Применить</button>
    </div>
  </div></div>
</div>

<!-- Модалка для массового тегирования -->
<div class="modal fade" id="bulkTagsModal" tabindex="-1">
  <div class="modal-dialog"><div class="modal-content bg-dark text-light">
    <div class="modal-header"><h5>Управление тегами</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div>
    <div class="modal-body">
      <div class="mb-2">
        <label class="me-3"><input type="radio" name="bulk_tag_mode" value="add" checked> Добавить теги</label>
        <label><input type="radio" name="bulk_tag_mode" value="replace"> Заменить теги</label>
      </div>
      <div class="input-group input-group-sm">
        <input type="text" class="form-control" name="tags" placeholder="Теги через запятую">
      </div>
    </div>
    <div class="modal-footer">
      <button type="button" class="btn btn-primary" onclick="executeBulkTags()">Применить</button>
    </div>
  </div></div>
</div>

<script>
// Массовые операции
function toggleAll(source) {
    document.querySelectorAll('.bulk-check').forEach(cb => cb.checked = source.checked);
    updateBulkPanel();
}

function updateBulkPanel() {
    const checked = document.querySelectorAll('.bulk-check:checked');
    document.getElementById('selected-count').textContent = checked.length;
    document.getElementById('bulk-actions').style.display = checked.length > 0 ? 'block' : 'none';
}

function getSelectedIds() {
    return Array.from(document.querySelectorAll('.bulk-check:checked')).map(cb => cb.value);
}

function clearBulkSelection() {
    document.querySelectorAll('.bulk-check').forEach(cb => cb.checked = false);
    document.getElementById('select-all').checked = false;
    updateBulkPanel();
}

async function bulkAction(entity, action) {
    const ids = getSelectedIds();
    if (ids.length === 0) { alert('Не выбраны кампании'); return; }

    if (action === 'set_group_prompt') {
        new bootstrap.Modal(document.getElementById('bulkGroupModal')).show();
        return;
    }
    if (action === 'set_tags_prompt') {
        new bootstrap.Modal(document.getElementById('bulkTagsModal')).show();
        return;
    }

    const resp = await fetch('/campaigns/bulk-action', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ action, ids })
    });
    const data = await resp.json();
    if (data.success) { location.reload(); }
    else { alert('Ошибка: ' + (data.error || 'неизвестно')); }
}

async function executeBulkGroup() {
    const ids = getSelectedIds();
    const group_id = document.getElementById('bulk_group_select').value || null;
    const resp = await fetch('/campaigns/bulk-action', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ action: 'set_group', ids, group_id })
    });
    const data = await resp.json();
    if (data.success) { location.reload(); }
    else { alert('Ошибка: ' + (data.error || 'неизвестно')); }
}

async function executeBulkTags() {
    const ids = getSelectedIds();
    const mode = document.querySelector('input[name="bulk_tag_mode"]:checked').value;
    const tags = document.querySelector('#bulkTagsModal input[name="tags"]').value;
    const resp = await fetch('/campaigns/bulk-action', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ action: 'set_tags', ids, tags, tag_mode: mode })
    });
    const data = await resp.json();
    if (data.success) { location.reload(); }
    else { alert('Ошибка: ' + (data.error || 'неизвестно')); }
}

// Загрузка ссылок
async function loadLinks(id) {
  if (!document.getElementById('linksModal')) {
    document.body.insertAdjacentHTML('beforeend', 
      '<div class="modal fade" id="linksModal" tabindex="-1">' +
      '<div class="modal-dialog modal-lg"><div class="modal-content bg-dark text-light">' +
      '<div class="modal-header"><h5>Ссылки для залива</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div>' +
      '<div class="modal-body" id="linksContent">Загрузка...</div>' +
      '</div></div></div>');
  }
  const linksContent = document.getElementById('linksContent');
  if (!linksContent) return;
  linksContent.innerHTML = 'Загрузка...';
  try {
    const resp = await fetch('/campaign/links/' + id);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const html = await resp.text();
    linksContent.innerHTML = html;
    new bootstrap.Modal(document.getElementById('linksModal')).show();
  } catch (e) {
    linksContent.innerHTML = '<div class="alert alert-danger">Ошибка загрузки ссылок</div>';
    console.error(e);
  }
}

async function openSubReport() {
    // Открываем модалку и загружаем данные по умолчанию (sub1)
    const modal = new bootstrap.Modal(document.getElementById('subReportModal'));
    modal.show();
    await loadSubReport();
}

async function loadSubReport() {
    const dim = document.getElementById('subReportDim').value;
    try {
        const resp = await fetch(`/campaigns/sub-report?dim=${dim}`);
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        if (!data.success) {
            alert('Ошибка загрузки отчёта');
            return;
        }
        renderSubReport(data.rows);
    } catch (e) {
        console.error(e);
        alert('Не удалось загрузить Sub-отчёт');
    }
}

function renderSubReport(rows) {
    const tbody = document.querySelector('#subReportTable tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    if (!rows || rows.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center">Нет данных</td></tr>';
        return;
    }
    for (const r of rows) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${escapeHtml(r.value)}</td>
            <td>${r.clicks}</td>
            <td>${r.leads}</td>
            <td>${r.approved}</td>
            <td>$${r.revenue.toFixed(2)}</td>
            <td>$${r.cost.toFixed(4)}</td>
            <td>${r.roi.toFixed(1)}%</td>
        `;
        tbody.appendChild(tr);
    }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
</script>
''' + FOOTER

EDIT_CAMPAIGN_MODAL_HTML = '''
<div class="modal fade" id="editCampaignModal" tabindex="-1">
  <div class="modal-dialog modal-xl">
    <form class="modal-content" method="post" action="/campaign/edit/{{camp['id']}}" id="editCampaignForm">
      <div class="modal-header">
        <h5>Редактировать кампанию #{{camp['id']}}</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        <!-- Основные настройки -->
        <div class="card bg-dark mb-3">
          <div class="card-header">Основные настройки</div>
          <div class="card-body">
            <div class="row mb-3">
              <div class="col-md-6">
                <label class="form-label">Название</label>
                <input class="form-control" name="name" value="{{camp['name']}}" required>
              </div>
              <div class="col-md-6">
                <label class="form-label">Домен</label>
                <select class="form-select" name="domain_id">
                  <option value="">-- По умолчанию --</option>
                  {% for d in domains %}<option value="{{d[0]}}" {{'selected' if d[0]==camp['domain_id'] else ''}}>{{d[1]}}</option>{% endfor %}
                </select>
              </div>
            </div>
            <div class="row mb-3">
              <div class="col-md-4">
                <label class="form-label">Лендинг по умолчанию</label>
                <select class="form-select" name="lander_id">
                  <option value="">-- Не выбран --</option>
                  {% for l in landers %}<option value="{{l[0]}}" {{'selected' if l[0]==camp['lander_id'] else ''}}>{{l[1]}}</option>{% endfor %}
                </select>
              </div>
              <div class="col-md-4">
                <label class="form-label">Оффер по умолчанию</label>
                <select class="form-select" name="offer_id">
                  <option value="">-- Не выбран --</option>
                  {% for o in offers %}<option value="{{o[0]}}" {{'selected' if o[0]==camp['offer_id'] else ''}}>{{o[1]}}</option>{% endfor %}
                </select>
              </div>
              <div class="col-md-4">
                <label class="form-label">Источник трафика</label>
                <select class="form-select" name="source_id">
                  <option value="">-- Не выбран --</option>
                  {% for s in sources %}<option value="{{s[0]}}" {{'selected' if s[0]==camp['traffic_source_id'] else ''}}>{{s[1]}}</option>{% endfor %}
                </select>
              </div>
            </div>
            <div class="row mb-3">
              <div class="col-md-4">
                <label class="form-label">Партнёрская сеть</label>
                <select class="form-select" name="network_id">
                  <option value="">-- Не выбрана --</option>
                  {% for n in networks %}<option value="{{n[0]}}" {{'selected' if n[0]==camp['affiliate_network_id'] else ''}}>{{n[1]}}</option>{% endfor %}
                </select>
              </div>
              <div class="col-md-4">
                <label class="form-label">JS-челлендж</label>
                <div class="form-check">
                  <input class="form-check-input" type="checkbox" name="js_challenge_enabled" {{'checked' if camp['js_challenge_enabled'] else ''}}>
                  <label class="form-check-label">Включить</label>
                </div>
                <select class="form-select form-select-sm mt-1" name="js_challenge_level">
                  <option value="super_easy" {{'selected' if camp['js_challenge_level']=='super_easy' else ''}}>Супер простой</option>
                  <option value="easy" {{'selected' if camp['js_challenge_level']=='easy' else ''}}>Простой</option>
                  <option value="medium" {{'selected' if camp['js_challenge_level']=='medium' else ''}}>Средний</option>
                </select>
              </div>
              <div class="col-md-4">
                <label class="form-label">S2S постбек URL</label>
                <input class="form-control" name="s2s_postback_url" value="{{ camp['s2s_postback_url'] or '' }}">
              </div>
            </div>
            <div class="row">
              <div class="col-md-12">
                <label class="form-label">Чёрный список IP</label>
                <textarea class="form-control" name="ip_blacklist" rows="2">{{ camp['ip_blacklist'] or '' }}</textarea>
              </div>
              <div class="col-md-12 mt-2">
                <label class="form-label">Белый список IP</label>
                <textarea class="form-control" name="ip_whitelist" rows="2">{{ camp['ip_whitelist'] or '' }}</textarea>
              </div>
            </div>
          </div>
        </div>

        <!-- Теги и страны -->
        <div class="card bg-dark mb-3">
          <div class="card-header">Теги и страны</div>
          <div class="card-body">
            <div class="row">
              <div class="col-md-6">
                <label class="form-label">Теги</label>
                <div class="tag-picker" data-name="edit_campaign_tags">
                  <div class="selected-tags mb-2"></div>
                  <div class="input-group input-group-sm">
                    <input type="text" class="form-control tag-search" placeholder="Поиск или новый тег">
                    <button type="button" class="btn btn-sm btn-outline-warning tag-create-btn">+ Создать</button>
                  </div>
                  <div class="tag-dropdown bg-dark p-2 mt-1 rounded" style="max-height:200px;overflow-y:auto;display:none;position:absolute;z-index:1000;width:100%;border:1px solid #e2a03f;">
                    {% for tag in AVAILABLE_TAGS %}
                      {% set color = TAG_COLOR_MAP.get(tag, '#95a5a6') %}
                      <div class="form-check">
                        <input class="form-check-input tag-check" type="checkbox" value="{{ tag }}" id="edit_tag_{{ tag }}">
                        <label class="form-check-label" for="edit_tag_{{ tag }}">
                          <span class="badge" style="background-color:{{ color }};margin-right:5px;">&nbsp;</span> {{ tag }}
                        </label>
                      </div>
                    {% endfor %}
                  </div>
                  <input type="hidden" name="tags" value="{{ camp['tags'] or '' }}">
                </div>
              </div>
              <div class="col-md-6">
                <label class="form-label">Страны</label>
                <div class="country-picker" data-name="countries_json" data-selected='{{ camp['countries_list']|tojson|safe }}'>
                  <div class="selected-countries mb-2"></div>
                  <input type="text" class="form-control form-control-sm country-search" placeholder="Поиск страны...">
                  <div class="country-dropdown bg-dark p-2 mt-1 rounded" style="max-height:200px;overflow-y:auto;display:none;position:absolute;z-index:1000;width:100%;border:1px solid #e2a03f;">
                    {% for code, name in COUNTRY_CODES.items() %}
                    <div class="form-check">
                      <input class="form-check-input country-check" type="checkbox" value="{{ code }}" id="edit_country_{{ code }}">
                      <label class="form-check-label" for="edit_country_{{ code }}">{{ code }} - {{ name }}</label>
                    </div>
                    {% endfor %}
                  </div>
                  <select multiple name="countries_json" style="display:none;"></select>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Пути и распределение трафика -->
        <div class="card bg-dark mb-3">
          <div class="card-header">Пути (процентный сплит)</div>
          <div class="card-body">
            <div id="pathsContainer">
              {% for p in paths %}
              <div class="row mb-2 align-items-center path-row">
                <div class="col-md-3">
                  <select class="form-select form-select-sm" name="path_lander_{{ loop.index0 }}">
                    <option value="">-- Лендинг --</option>
                    {% for l in landers %}<option value="{{l[0]}}" {{'selected' if l[0]==p['lander_id'] else ''}}>{{l[1]}}</option>{% endfor %}
                  </select>
                </div>
                <div class="col-md-3">
                  <select class="form-select form-select-sm" name="path_offer_{{ loop.index0 }}">
                    <option value="">-- Оффер --</option>
                    {% for o in offers %}<option value="{{o[0]}}" {{'selected' if o[0]==p['offer_id'] else ''}}>{{o[1]}}</option>{% endfor %}
                  </select>
                </div>
                <div class="col-md-2">
                  <input type="number" class="form-control form-control-sm" name="path_percent_{{ loop.index0 }}" value="{{ p['value'] }}" min="0" max="100" oninput="updateSum()">
                </div>
                <div class="col-md-2">
                  <button type="button" class="btn btn-sm btn-outline-danger" onclick="this.closest('.path-row').remove(); updateSum()">✕</button>
                </div>
              </div>
              {% endfor %}
            </div>
            <button type="button" class="btn btn-sm btn-success" onclick="addPath()">➕ Добавить путь</button>
            <div class="mb-3"><strong>Сумма процентов: <span id="percentSum">0</span>%</strong></div>
          </div>
        </div>

        <!-- Правила клоакинга -->
        <div class="card bg-dark mb-3">
          <div class="card-header">Правила клоакинга</div>
          <div class="card-body">
            <div id="cloakRulesContainer">
              {% for r in rules %}
              <div class="row mb-2 align-items-center cloak-rule-row" data-rule-value="{{ r['value'] }}">
                <div class="col-md-2">
                  <select class="form-select form-select-sm" name="rule_condition_type_{{ loop.index0 }}" onchange="updateRuleValueControl(this, {{loop.index0}})">
                    <option value="country" {{'selected' if r['condition_type']=='country' else ''}}>Страна</option>
                    <option value="device" {{'selected' if r['condition_type']=='device' else ''}}>Устройство</option>
                    <option value="os" {{'selected' if r['condition_type']=='os' else ''}}>ОС</option>
                    <option value="browser" {{'selected' if r['condition_type']=='browser' else ''}}>Браузер</option>
                    <option value="bot_keywords" {{'selected' if r['condition_type']=='bot_keywords' else ''}}>Боты</option>
                  </select>
                </div>
                <div class="col-md-1">
                  <select class="form-select form-select-sm" name="rule_operator_{{ loop.index0 }}">
                    <option value="equals" {{'selected' if r['operator']=='equals' else ''}}>Равно</option>
                    <option value="not_equals" {{'selected' if r['operator']=='not_equals' else ''}}>Не равно</option>
                  </select>
                </div>
                <div class="col-md-2" id="rule_value_container_{{ loop.index0 }}">
                  <!-- значение подставится скриптом -->
                </div>
                <div class="col-md-2">
                  <select class="form-select form-select-sm" name="rule_action_{{ loop.index0 }}">
                    <option value="allow_path" {{'selected' if r['action']=='allow_path' else ''}}>Показать путь</option>
                    <option value="block" {{'selected' if r['action']=='block' else ''}}>Заблокировать</option>
                    <option value="allow_default" {{'selected' if r['action']=='allow_default' else ''}}>По умолчанию</option>
                  </select>
                </div>
                <div class="col-md-2">
                  <select class="form-select form-select-sm" name="rule_lander_{{ loop.index0 }}">
                    <option value="">-- Лендинг --</option>
                    {% for l in landers %}<option value="{{l[0]}}" {{'selected' if l[0]==r['lander_id'] else ''}}>{{l[1]}}</option>{% endfor %}
                  </select>
                </div>
                <div class="col-md-2">
                  <select class="form-select form-select-sm" name="rule_offer_{{ loop.index0 }}">
                    <option value="">-- Оффер --</option>
                    {% for o in offers %}<option value="{{o[0]}}" {{'selected' if o[0]==r['offer_id'] else ''}}>{{o[1]}}</option>{% endfor %}
                  </select>
                </div>
                <div class="col-md-1">
                  <input class="form-check-input" type="checkbox" name="rule_js_{{ loop.index0 }}" {{'checked' if r['js_challenge'] else ''}}>
                </div>
                <div class="col-md-1">
                  <button type="button" class="btn btn-sm btn-outline-danger" onclick="this.closest('.cloak-rule-row').remove()">✕</button>
                </div>
              </div>
              {% endfor %}
            </div>
            <button type="button" class="btn btn-sm btn-success" onclick="addCloakRule()">➕ Добавить правило</button>
          </div>
        </div>

        <!-- Кастомные макросы -->
        <div class="card bg-dark mb-3">
          <div class="card-header">Кастомные макросы</div>
          <div class="card-body">
            <div class="row g-2">
              <div class="col-md-6">
                <label class="form-label">cost</label>
                <input class="form-control form-control-sm" name="macro_cost" value="{{ mapping.get('cost', '') if mapping else '' }}">
              </div>
              <div class="col-md-6">
                <label class="form-label">click_id</label>
                <input class="form-control form-control-sm" name="macro_click_id" value="{{ mapping.get('click_id', '') if mapping else '' }}">
              </div>
              <div class="col-md-6">
                <label class="form-label">payout</label>
                <input class="form-control form-control-sm" name="macro_payout" value="{{ mapping.get('payout', '') if mapping else '' }}">
              </div>
              <div class="col-md-6">
                <label class="form-label">goal</label>
                <input class="form-control form-control-sm" name="macro_goal" value="{{ mapping.get('goal', '') if mapping else '' }}">
              </div>
              {% for i in range(1, 12) %}
              <div class="col-md-4">
                <label class="form-label">sub{{ i }}</label>
                <input class="form-control form-control-sm" name="macro_sub{{ i }}" value="{{ mapping.get('sub' ~ i, '') if mapping else '' }}">
              </div>
              {% endfor %}
            </div>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <input type="hidden" name="path_count" id="edit_path_count" value="{{ paths|length }}">
        <input type="hidden" name="rule_count" id="edit_rule_count" value="{{ rules|length }}">
        <button type="submit" class="btn btn-primary">Сохранить</button>
      </div>
    </form>
  </div>
</div>

<script>
window.landers = {{ landers|tojson|safe }};
window.offers = {{ offers|tojson|safe }};
window.COUNTRY_CODES = {{ COUNTRY_CODES|tojson|safe }};

document.getElementById('editCampaignForm').addEventListener('submit', function(e) {
    const pathCount = this.querySelectorAll('.path-row').length;
    const ruleCount = this.querySelectorAll('.cloak-rule-row').length;
    this.querySelector('input[name="path_count"]').value = pathCount;
    this.querySelector('input[name="rule_count"]').value = ruleCount;
});
</script>
'''

LANDERS_HTML = HEADER + '''
{% set c = {} %}
<h4>Лендинги <button class="btn btn-primary btn-sm float-end" data-bs-toggle="modal" data-bs-target="#createLanderModal">Создать</button></h4>

<div id="bulk-actions-landers" class="mb-3 p-2 bg-dark rounded" style="display:none;">
  <span class="text-warning me-2">Выбрано: <strong id="selected-count-landers">0</strong></span>
  <button class="btn btn-sm btn-outline-warning" onclick="bulkActionLander('trash')">🗑️ В корзину</button>
  <button class="btn btn-sm btn-outline-warning" onclick="bulkActionLander('set_group_prompt')">📁 Группа</button>
  <button class="btn btn-sm btn-outline-warning" onclick="bulkActionLander('set_tags_prompt')">🏷️ Теги</button>
  <button class="btn btn-sm btn-outline-danger" onclick="clearBulkSelectionLander()">✕ Сбросить</button>
</div>
<!-- Панель периода и экспорта -->
<form class="row g-2 mb-3" method="get" id="periodForm">
  <div class="col-auto">
    <select class="form-select form-select-sm" name="period" onchange="handlePeriodChange(this.value)">
      <option value="all" {{ 'selected' if period=='all' else '' }}>Всё время</option>
      <option value="today" {{ 'selected' if period=='today' else '' }}>Сегодня</option>
      <option value="yesterday" {{ 'selected' if period=='yesterday' else '' }}>Вчера</option>
      <option value="3days" {{ 'selected' if period=='3days' else '' }}>3 дня</option>
      <option value="week" {{ 'selected' if period=='week' else '' }}>Неделя</option>
      <option value="2weeks" {{ 'selected' if period=='2weeks' else '' }}>2 недели</option>
      <option value="month" {{ 'selected' if period=='month' else '' }}>Месяц</option>
      <option value="year" {{ 'selected' if period=='year' else '' }}>Год</option>
      <option value="custom" {{ 'selected' if period=='custom' else '' }}>Произвольный</option>
    </select>
  </div>
  <div class="col-auto" id="customDateFields" style="display: {{ 'block' if period=='custom' else 'none' }};">
    <input type="date" class="form-control form-control-sm d-inline w-auto" name="start" value="{{ start }}">
    <span class="text-light">—</span>
    <input type="date" class="form-control form-control-sm d-inline w-auto" name="end" value="{{ end }}">
  </div>
  <div class="col-auto">
    <button type="submit" class="btn btn-sm btn-outline-warning">Применить</button>
    <a href="/landers/export-csv?{{ request.query_string.decode() }}" class="btn btn-sm btn-info">📥 CSV</a>
  </div>
</form>
<script>
function handlePeriodChange(val) {
  document.getElementById('customDateFields').style.display = val === 'custom' ? 'block' : 'none';
  if (val !== 'custom') document.getElementById('periodForm').submit();
}
</script>
<div class="table-responsive">
<table class="table table-striped table-hover" id="landers-table">
<thead>
  <tr>
    <th><input type="checkbox" id="select-all-landers" onchange="toggleAllLander(this)"></th>
    <th>ID</th><th>Название</th><th>Группа</th><th>Тип</th>
    <th>Клики</th><th>Лиды</th><th>Аппрув</th><th>Аппрув-рейт</th>
    <th>Доход</th><th>Расход</th><th>Прибыль</th><th>ROI</th>
    <th>CPC</th><th>EPC</th><th>CR</th><th>Теги</th><th></th>
  </tr>
</thead>
<tbody>
{% for l in landers %}
{% set st = stats.get(l[0], {}) %}
{% set clicks = st.clicks|default(0) %}
{% set leads = st.leads|default(0) %}
{% set approved = st.approved|default(0) %}
{% set revenue = st.revenue|default(0.0) %}
{% set cost = st.cost|default(0.0) %}
{% set profit = revenue - cost %}
<tr>
  <td><input type="checkbox" class="bulk-check-lander" value="{{ l[0] }}" onchange="updateBulkPanelLander()"></td>
  <td>{{l[0]}}</td>
  <td>{{l[1]}}</td>
  <td>{{ groups_dict.get(l[2], '—') if groups_dict is defined else l[2] }}</td>
  <td>{{l[5]}}</td>
  <td>{{clicks}}</td>
  <td>{{leads}}</td>
  <td>{{approved}}</td>
  <td>{{ "%.1f"|format((approved/leads*100) if leads>0 else 0) }}%</td>
  <td>${{"%.2f"|format(revenue)}}</td>
  <td>${{"%.4f"|format(cost)}}</td>
  <td>${{"%.2f"|format(profit)}}</td>
  <td>{{"%.1f"|format((profit/cost*100) if cost>0 else 0)}}%</td>
  <td>${{"%.4f"|format((cost/clicks) if clicks>0 else 0)}}</td>
  <td>${{"%.4f"|format((revenue/clicks) if clicks>0 else 0)}}</td>
  <td>{{"%.2f"|format((leads/clicks*100) if clicks>0 else 0)}}%</td>
  <td>
    {% for t in l[7].split(',') if t.strip() %}
      {% set color = TAG_COLOR_MAP.get(t.strip(), '#95a5a6') %}
      <span class="badge" style="background-color:{{color}}">{{t.strip()}}</span>
    {% endfor %}
  </td>
  <td>
    <button class="btn btn-sm btn-warning" 
            hx-get="/campaign/edit/{{c[0]}}/form" 
            hx-target="#modal-container" 
            hx-swap="innerHTML">✎</button></form>
  </td>
</tr>
{% endfor %}</tbody></table>
</div>

<!-- Модалка для массового выбора группы -->
<div class="modal fade" id="bulkGroupModalLander" tabindex="-1">
  <div class="modal-dialog"><div class="modal-content bg-dark text-light">
    <div class="modal-header"><h5>Назначить группу</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div>
    <div class="modal-body">
      <div class="input-group input-group-sm">
        <select class="form-select" id="bulk_group_select_lander">
          <option value="">-- Без группы --</option>
          {% for g in groups %}
          <option value="{{ g[0] }}">{{ g[1] }}</option>
          {% endfor %}
        </select>
        <button type="button" class="btn btn-sm btn-outline-warning" onclick="createGroup(document.getElementById('bulk_group_select_lander'))">+</button>
      </div>
    </div>
    <div class="modal-footer">
      <button type="button" class="btn btn-primary" onclick="executeBulkGroupLander()">Применить</button>
    </div>
  </div></div>
</div>

<!-- Модалка для массового тегирования -->
<div class="modal fade" id="bulkTagsModalLander" tabindex="-1">
  <div class="modal-dialog"><div class="modal-content bg-dark text-light">
    <div class="modal-header"><h5>Управление тегами</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div>
    <div class="modal-body">
      <div class="mb-2">
        <label class="me-3"><input type="radio" name="bulk_tag_mode_lander" value="add" checked> Добавить теги</label>
        <label><input type="radio" name="bulk_tag_mode_lander" value="replace"> Заменить теги</label>
      </div>
      <div class="tag-picker" data-name="bulk_tags_lander">
        <div class="selected-tags mb-2"></div>
        <div class="input-group input-group-sm">
          <input type="text" class="form-control tag-search" placeholder="Поиск или новый тег">
          <button type="button" class="btn btn-sm btn-outline-warning tag-create-btn">+ Создать</button>
        </div>
        <div class="tag-dropdown bg-dark p-2 mt-1 rounded" style="max-height:200px;overflow-y:auto;display:none;position:absolute;z-index:1000;width:100%;border:1px solid #e2a03f;">
          {% for tag in AVAILABLE_TAGS %}
            {% set color = TAG_COLOR_MAP.get(tag, '#95a5a6') %}
            <div class="form-check">
              <input class="form-check-input tag-check" type="checkbox" value="{{ tag }}" id="bulk_lander_tag_{{ tag }}">
              <label class="form-check-label" for="bulk_lander_tag_{{ tag }}">
                <span class="badge" style="background-color:{{ color }};margin-right:5px;">&nbsp;</span> {{ tag }}
              </label>
            </div>
          {% endfor %}
        </div>
        <input type="hidden" name="tags" value="">
      </div>
    </div>
    <div class="modal-footer">
      <button type="button" class="btn btn-primary" onclick="executeBulkTagsLander()">Применить</button>
    </div>
  </div></div>
</div>

<!-- Модалки редактирования -->
{% for l in landers %}
<div class="modal fade" id="editLanderModal{{l[0]}}" tabindex="-1"><div class="modal-dialog"><form class="modal-content" method="post" action="/lander/edit/{{l[0]}}"><div class="modal-header"><h5>Редактировать лендинг</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div><div class="modal-body">
  <label>Название</label><input class="form-control" name="name" value="{{l[1]}}" required>
  
  <label>Группа</label>
  <div class="input-group input-group-sm">
    <select class="form-select" name="group_id" id="group_select_edit_lander_{{ l[0] }}">
      <option value="">-- Без группы --</option>
      {% for g in groups %}
      <option value="{{ g[0] }}" {{ 'selected' if g[0] == l[2] else '' }}>{{ g[1] }}</option>
      {% endfor %}
    </select>
    <button type="button" class="btn btn-sm btn-outline-warning" onclick="createGroup(document.getElementById('group_select_edit_lander_{{ l[0] }}'))">+</button>
  </div>

  <label>Теги</label>
  <div class="tag-picker" data-name="edit_lander_tags_{{ l[0] }}">
    <div class="selected-tags mb-2"></div>
    <div class="input-group input-group-sm">
      <input type="text" class="form-control tag-search" placeholder="Поиск или новый тег">
      <button type="button" class="btn btn-sm btn-outline-warning tag-create-btn">+ Создать</button>
    </div>
    <div class="tag-dropdown bg-dark p-2 mt-1 rounded" style="max-height:200px;overflow-y:auto;display:none;position:absolute;z-index:1000;width:100%;border:1px solid #e2a03f;">
      {% for tag in AVAILABLE_TAGS %}
        {% set color = TAG_COLOR_MAP.get(tag, '#95a5a6') %}
        <div class="form-check">
          <input class="form-check-input tag-check" type="checkbox" value="{{ tag }}" id="edit_lander_tag_{{ l[0] }}_{{ tag }}">
          <label class="form-check-label" for="edit_lander_tag_{{ l[0] }}_{{ tag }}">
            <span class="badge" style="background-color:{{ color }};margin-right:5px;">&nbsp;</span> {{ tag }}
          </label>
        </div>
      {% endfor %}
    </div>
    <input type="hidden" name="tags" value="{{ l[7] }}">
  </div>

  <label>URL</label><input class="form-control" name="url" value="{{l[3]}}">
  <details>
    <summary style="cursor:pointer; color:var(--accent);">Дополнительно</summary>
    <label>Язык</label><input class="form-control" name="language" value="{{l[4]}}">
    <label>Индексный файл</label><input class="form-control" name="index_file" value="{{l[6] or 'index.html'}}">
  </details>
</div><div class="modal-footer"><button class="btn btn-primary">Сохранить</button></div></form></div></div>
{% endfor %}

<div class="modal fade" id="createLanderModal" tabindex="-1"><div class="modal-dialog"><form class="modal-content" method="post" action="/lander/create" enctype="multipart/form-data"><div class="modal-header"><h5>Новый лендинг</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div><div class="modal-body">
  <label>Название</label><input class="form-control" name="name" required>

  <label>Группа</label>
  <div class="input-group input-group-sm">
    <select class="form-select" name="group_id" id="group_select_create_lander">
      <option value="">-- Без группы --</option>
      {% for g in groups %}
      <option value="{{ g[0] }}">{{ g[1] }}</option>
      {% endfor %}
    </select>
    <button type="button" class="btn btn-sm btn-outline-warning" onclick="createGroup(document.getElementById('group_select_create_lander'))">+</button>
  </div>

  <label>Теги</label>
  <div class="tag-picker" data-name="create_lander_tags">
    <div class="selected-tags mb-2"></div>
    <div class="input-group input-group-sm">
      <input type="text" class="form-control tag-search" placeholder="Поиск или новый тег">
      <button type="button" class="btn btn-sm btn-outline-warning tag-create-btn">+ Создать</button>
    </div>
    <div class="tag-dropdown bg-dark p-2 mt-1 rounded" style="max-height:200px;overflow-y:auto;display:none;position:absolute;z-index:1000;width:100%;border:1px solid #e2a03f;">
      {% for tag in AVAILABLE_TAGS %}
        {% set color = TAG_COLOR_MAP.get(tag, '#95a5a6') %}
        <div class="form-check">
          <input class="form-check-input tag-check" type="checkbox" value="{{ tag }}" id="create_lander_tag_{{ tag }}">
          <label class="form-check-label" for="create_lander_tag_{{ tag }}">
            <span class="badge" style="background-color:{{ color }};margin-right:5px;">&nbsp;</span> {{ tag }}
          </label>
        </div>
      {% endfor %}
    </div>
    <input type="hidden" name="tags" value="">
  </div>

  <label>Тип</label>
  <select class="form-select" name="type" id="landerType" onchange="toggleLanderFields()">
    <option value="url">URL</option>
    <option value="file">Загрузить ZIP</option>
    <option value="html">Свой HTML-код</option>
  </select>
  <div id="urlField"><label>URL</label><input class="form-control" name="url"></div>
  <div id="zipField" style="display:none"><label>ZIP файл</label><input class="form-control" type="file" name="file" accept=".zip"></div>
  <div id="htmlField" style="display:none"><label>HTML код</label><textarea class="form-control" name="html_code" rows="10" style="font-family:monospace;"></textarea></div>
  <details>
    <summary style="cursor:pointer; color:var(--accent);">Дополнительно</summary>
    <label>Язык</label><input class="form-control" name="language" placeholder="ru, en">
    <label>Индексный файл</label><input class="form-control" name="index_file" placeholder="index.html">
  </details>
</div><div class="modal-footer"><button class="btn btn-primary">Создать</button></div></form></div></div>
<script>
  function toggleLanderFields() {
    const type = document.getElementById('landerType').value;
    document.getElementById('urlField').style.display = type === 'url' ? 'block' : 'none';
    document.getElementById('zipField').style.display = type === 'file' ? 'block' : 'none';
    document.getElementById('htmlField').style.display = type === 'html' ? 'block' : 'none';
  }

  // --- Массовые действия ---
  function toggleAllLander(source) {
    document.querySelectorAll('.bulk-check-lander').forEach(cb => cb.checked = source.checked);
    updateBulkPanelLander();
  }

  function updateBulkPanelLander() {
    const checked = document.querySelectorAll('.bulk-check-lander:checked');
    const count = checked.length;
    document.getElementById('selected-count-landers').textContent = count;
    document.getElementById('bulk-actions-landers').style.display = count > 0 ? 'block' : 'none';
  }

  function getSelectedIdsLander() {
    return Array.from(document.querySelectorAll('.bulk-check-lander:checked')).map(cb => cb.value);
  }

  function clearBulkSelectionLander() {
    document.querySelectorAll('.bulk-check-lander').forEach(cb => cb.checked = false);
    document.getElementById('select-all-landers').checked = false;
    updateBulkPanelLander();
  }

  async function bulkActionLander(action) {
    const ids = getSelectedIdsLander();
    if (ids.length === 0) { alert('Не выбраны элементы'); return; }

    if (action === 'set_group_prompt') {
      new bootstrap.Modal(document.getElementById('bulkGroupModalLander')).show();
      return;
    }
    if (action === 'set_tags_prompt') {
      new bootstrap.Modal(document.getElementById('bulkTagsModalLander')).show();
      return;
    }

    const resp = await fetch('/landers/bulk-action', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ action, ids })
    });
    const data = await resp.json();
    if (data.success) { location.reload(); }
    else { alert('Ошибка: ' + (data.error || 'неизвестно')); }
  }

  async function executeBulkGroupLander() {
    const ids = getSelectedIdsLander();
    const group_id = document.getElementById('bulk_group_select_lander').value || null;
    const resp = await fetch('/landers/bulk-action', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ action: 'set_group', ids, group_id })
    });
    const data = await resp.json();
    if (data.success) { location.reload(); }
    else { alert('Ошибка: ' + (data.error || 'неизвестно')); }
  }

  async function executeBulkTagsLander() {
    const ids = getSelectedIdsLander();
    const mode = document.querySelector('input[name="bulk_tag_mode_lander"]:checked').value;
    const tags = document.querySelector('#bulkTagsModalLander input[name="tags"]').value;
    const resp = await fetch('/landers/bulk-action', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ action: 'set_tags', ids, tags, tag_mode: mode })
    });
    const data = await resp.json();
    if (data.success) { location.reload(); }
    else { alert('Ошибка: ' + (data.error || 'неизвестно')); }
  }
</script>
''' + FOOTER

OFFERS_HTML = HEADER + '''<h4>Офферы <button class="btn btn-primary btn-sm float-end" data-bs-toggle="modal" data-bs-target="#createOfferModal">Создать</button></h4>

<div id="bulk-actions-offers" class="mb-3 p-2 bg-dark rounded" style="display:none;">
  <span class="text-warning me-2">Выбрано: <strong id="selected-count-offers">0</strong></span>
  <button class="btn btn-sm btn-outline-warning" onclick="bulkActionOffer('trash')">🗑️ В корзину</button>
  <button class="btn btn-sm btn-outline-warning" onclick="bulkActionOffer('set_group_prompt')">📁 Группа</button>
  <button class="btn btn-sm btn-outline-warning" onclick="bulkActionOffer('set_tags_prompt')">🏷️ Теги</button>
  <button class="btn btn-sm btn-outline-danger" onclick="clearBulkSelectionOffer()">✕ Сбросить</button>
</div>
<!-- Панель периода и экспорта -->
<form class="row g-2 mb-3" method="get" id="periodForm">
  <div class="col-auto">
    <select class="form-select form-select-sm" name="period" onchange="handlePeriodChange(this.value)">
      <option value="all" {{ 'selected' if period=='all' else '' }}>Всё время</option>
      <option value="today" {{ 'selected' if period=='today' else '' }}>Сегодня</option>
      <option value="yesterday" {{ 'selected' if period=='yesterday' else '' }}>Вчера</option>
      <option value="3days" {{ 'selected' if period=='3days' else '' }}>3 дня</option>
      <option value="week" {{ 'selected' if period=='week' else '' }}>Неделя</option>
      <option value="2weeks" {{ 'selected' if period=='2weeks' else '' }}>2 недели</option>
      <option value="month" {{ 'selected' if period=='month' else '' }}>Месяц</option>
      <option value="year" {{ 'selected' if period=='year' else '' }}>Год</option>
      <option value="custom" {{ 'selected' if period=='custom' else '' }}>Произвольный</option>
    </select>
  </div>
  <div class="col-auto" id="customDateFields" style="display: {{ 'block' if period=='custom' else 'none' }};">
    <input type="date" class="form-control form-control-sm d-inline w-auto" name="start" value="{{ start }}">
    <span class="text-light">—</span>
    <input type="date" class="form-control form-control-sm d-inline w-auto" name="end" value="{{ end }}">
  </div>
  <div class="col-auto">
    <button type="submit" class="btn btn-sm btn-outline-warning">Применить</button>
    <a href="/offers/export-csv?{{ request.query_string.decode() }}" class="btn btn-sm btn-info">📥 CSV</a>
  </div>
</form>
<script>
function handlePeriodChange(val) {
  document.getElementById('customDateFields').style.display = val === 'custom' ? 'block' : 'none';
  if (val !== 'custom') document.getElementById('periodForm').submit();
}
</script>
<div class="table-responsive">
<table class="table table-striped table-hover" id="offers-table">
<thead>
  <tr>
    <th><input type="checkbox" id="select-all-offers" onchange="toggleAllOffer(this)"></th>
    <th>ID</th><th>Название</th><th>Группа</th><th>Выплата</th>
    <th>Клики</th><th>Лиды</th><th>Аппрув</th><th>Аппрув-рейт</th>
    <th>Доход</th><th>Расход</th><th>Прибыль</th><th>ROI</th>
    <th>CPC</th><th>EPC</th><th>CR</th><th>Теги</th><th></th>
  </tr>
</thead>
<tbody>
{% for o in offers %}
{% set st = stats.get(o[0], {}) %}
{% set clicks = st.clicks|default(0) %}
{% set leads = st.leads|default(0) %}
{% set approved = st.approved|default(0) %}
{% set revenue = st.revenue|default(0.0) %}
{% set cost = st.cost|default(0.0) %}
{% set profit = revenue - cost %}
<tr>
  <td><input type="checkbox" class="bulk-check-offer" value="{{ o[0] }}" onchange="updateBulkPanelOffer()"></td>
  <td>{{o[0]}}</td>
  <td>{{o[1]}}</td>
  <td>{{ groups_dict.get(o[2], '—') if groups_dict is defined else o[2] }}</td>
  <td>${{"%.2f"|format(o[5])}}</td>
  <td>{{clicks}}</td>
  <td>{{leads}}</td>
  <td>{{approved}}</td>
  <td>{{ "%.1f"|format((approved/leads*100) if leads>0 else 0) }}%</td>
  <td>${{"%.2f"|format(revenue)}}</td>
  <td>${{"%.4f"|format(cost)}}</td>
  <td>${{"%.2f"|format(profit)}}</td>
  <td>{{"%.1f"|format((profit/cost*100) if cost>0 else 0)}}%</td>
  <td>${{"%.4f"|format((cost/clicks) if clicks>0 else 0)}}</td>
  <td>${{"%.4f"|format((revenue/clicks) if clicks>0 else 0)}}</td>
  <td>{{"%.2f"|format((leads/clicks*100) if clicks>0 else 0)}}%</td>
  <td>
    {% for t in o[14].split(',') if t.strip() %}
      {% set color = TAG_COLOR_MAP.get(t.strip(), '#95a5a6') %}
      <span class="badge" style="background-color:{{color}}">{{t.strip()}}</span>
    {% endfor %}
  </td>
  <td>
    <button class="btn btn-sm btn-warning" data-bs-toggle="modal" data-bs-target="#editOfferModal{{o[0]}}">✎</button>
    <form method="post" action="/offer/delete/{{o[0]}}" style="display:inline"><button class="btn btn-sm btn-danger">🗑</button></form>
  </td>
</tr>
{% endfor %}</tbody></table>
</div>

<!-- Модалка для массового выбора группы -->
<div class="modal fade" id="bulkGroupModalOffer" tabindex="-1">
  <div class="modal-dialog"><div class="modal-content bg-dark text-light">
    <div class="modal-header"><h5>Назначить группу</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div>
    <div class="modal-body">
      <div class="input-group input-group-sm">
        <select class="form-select" id="bulk_group_select_offer">
          <option value="">-- Без группы --</option>
          {% for g in groups %}
          <option value="{{ g[0] }}">{{ g[1] }}</option>
          {% endfor %}
        </select>
        <button type="button" class="btn btn-sm btn-outline-warning" onclick="createGroup(document.getElementById('bulk_group_select_offer'))">+</button>
      </div>
    </div>
    <div class="modal-footer">
      <button type="button" class="btn btn-primary" onclick="executeBulkGroupOffer()">Применить</button>
    </div>
  </div></div>
</div>

<!-- Модалка для массового тегирования -->
<div class="modal fade" id="bulkTagsModalOffer" tabindex="-1">
  <div class="modal-dialog"><div class="modal-content bg-dark text-light">
    <div class="modal-header"><h5>Управление тегами</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div>
    <div class="modal-body">
      <div class="mb-2">
        <label class="me-3"><input type="radio" name="bulk_tag_mode_offer" value="add" checked> Добавить теги</label>
        <label><input type="radio" name="bulk_tag_mode_offer" value="replace"> Заменить теги</label>
      </div>
      <div class="tag-picker" data-name="bulk_tags_offer">
        <div class="selected-tags mb-2"></div>
        <div class="input-group input-group-sm">
          <input type="text" class="form-control tag-search" placeholder="Поиск или новый тег">
          <button type="button" class="btn btn-sm btn-outline-warning tag-create-btn">+ Создать</button>
        </div>
        <div class="tag-dropdown bg-dark p-2 mt-1 rounded" style="max-height:200px;overflow-y:auto;display:none;position:absolute;z-index:1000;width:100%;border:1px solid #e2a03f;">
          {% for tag in AVAILABLE_TAGS %}
            {% set color = TAG_COLOR_MAP.get(tag, '#95a5a6') %}
            <div class="form-check">
              <input class="form-check-input tag-check" type="checkbox" value="{{ tag }}" id="bulk_offer_tag_{{ tag }}">
              <label class="form-check-label" for="bulk_offer_tag_{{ tag }}">
                <span class="badge" style="background-color:{{ color }};margin-right:5px;">&nbsp;</span> {{ tag }}
              </label>
            </div>
          {% endfor %}
        </div>
        <input type="hidden" name="tags" value="">
      </div>
    </div>
    <div class="modal-footer">
      <button type="button" class="btn btn-primary" onclick="executeBulkTagsOffer()">Применить</button>
    </div>
  </div></div>
</div>

<!-- Модалки редактирования -->
{% for o in offers %}
<div class="modal fade" id="editOfferModal{{o[0]}}" tabindex="-1"><div class="modal-dialog modal-lg"><form class="modal-content" method="post" action="/offer/edit/{{o[0]}}"><div class="modal-header"><h5>Редактировать оффер</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div><div class="modal-body"><div class="row"><div class="col">
  <label>Название</label><input class="form-control" name="name" value="{{o[1]}}" required>

  <label>Группа</label>
  <div class="input-group input-group-sm">
    <select class="form-select" name="group_id" id="group_select_edit_offer_{{ o[0] }}">
      <option value="">-- Без группы --</option>
      {% for g in groups %}
      <option value="{{ g[0] }}" {{ 'selected' if g[0] == o[2] else '' }}>{{ g[1] }}</option>
      {% endfor %}
    </select>
    <button type="button" class="btn btn-sm btn-outline-warning" onclick="createGroup(document.getElementById('group_select_edit_offer_{{ o[0] }}'))">+</button>
  </div>

  <label>Теги</label>
  <div class="tag-picker" data-name="edit_offer_tags_{{ o[0] }}">
    <div class="selected-tags mb-2"></div>
    <div class="input-group input-group-sm">
      <input type="text" class="form-control tag-search" placeholder="Поиск или новый тег">
      <button type="button" class="btn btn-sm btn-outline-warning tag-create-btn">+ Создать</button>
    </div>
    <div class="tag-dropdown bg-dark p-2 mt-1 rounded" style="max-height:200px;overflow-y:auto;display:none;position:absolute;z-index:1000;width:100%;border:1px solid #e2a03f;">
      {% for tag in AVAILABLE_TAGS %}
        {% set color = TAG_COLOR_MAP.get(tag, '#95a5a6') %}
        <div class="form-check">
          <input class="form-check-input tag-check" type="checkbox" value="{{ tag }}" id="edit_offer_tag_{{ o[0] }}_{{ tag }}">
          <label class="form-check-label" for="edit_offer_tag_{{ o[0] }}_{{ tag }}">
            <span class="badge" style="background-color:{{ color }};margin-right:5px;">&nbsp;</span> {{ tag }}
          </label>
        </div>
      {% endfor %}
    </div>
    <input type="hidden" name="tags" value="{{ o[14] }}">
  </div>

  <label>URL</label><input class="form-control" name="url" value="{{o[4]}}">
  <label>Выплата $</label><input class="form-control" name="payout" value="{{o[5]}}">
  <label>Страна</label><input class="form-control" name="country" value="{{o[6]}}">
</div><div class="col">
  <label>Лендинг по умолч.</label><select class="form-select" name="default_lander_id"><option value="">--</option>{% for l in landers %}<option value="{{l[0]}}" {{'selected' if o[13]==l[0]}}>{{l[1]}}</option>{% endfor %}</select>
  <label>Партнёрка</label><select class="form-select" name="network_id"><option value="">--</option>{% for n in networks %}<option value="{{n[0]}}" {{'selected' if o[3]==n[1]}}>{{n[1]}}</option>{% endfor %}</select>
</div></div></div><div class="modal-footer"><button class="btn btn-primary">Сохранить</button></div></form></div></div>
{% endfor %}

<div class="modal fade" id="createOfferModal" tabindex="-1"><div class="modal-dialog modal-lg"><form class="modal-content" method="post" action="/offer/create"><div class="modal-header"><h5>Новый оффер</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div><div class="modal-body"><div class="row"><div class="col">
  <label>Название</label><input class="form-control" name="name" required>

  <label>Группа</label>
  <div class="input-group input-group-sm">
    <select class="form-select" name="group_id" id="group_select_create_offer">
      <option value="">-- Без группы --</option>
      {% for g in groups %}
      <option value="{{ g[0] }}">{{ g[1] }}</option>
      {% endfor %}
    </select>
    <button type="button" class="btn btn-sm btn-outline-warning" onclick="createGroup(document.getElementById('group_select_create_offer'))">+</button>
  </div>

  <label>Теги</label>
  <div class="tag-picker" data-name="create_offer_tags">
    <div class="selected-tags mb-2"></div>
    <div class="input-group input-group-sm">
      <input type="text" class="form-control tag-search" placeholder="Поиск или новый тег">
      <button type="button" class="btn btn-sm btn-outline-warning tag-create-btn">+ Создать</button>
    </div>
    <div class="tag-dropdown bg-dark p-2 mt-1 rounded" style="max-height:200px;overflow-y:auto;display:none;position:absolute;z-index:1000;width:100%;border:1px solid #e2a03f;">
      {% for tag in AVAILABLE_TAGS %}
        {% set color = TAG_COLOR_MAP.get(tag, '#95a5a6') %}
        <div class="form-check">
          <input class="form-check-input tag-check" type="checkbox" value="{{ tag }}" id="create_offer_tag_{{ tag }}">
          <label class="form-check-label" for="create_offer_tag_{{ tag }}">
            <span class="badge" style="background-color:{{ color }};margin-right:5px;">&nbsp;</span> {{ tag }}
          </label>
        </div>
      {% endfor %}
    </div>
    <input type="hidden" name="tags" value="">
  </div>

  <label>URL</label><input class="form-control" name="url">
  <label>Выплата $</label><input class="form-control" name="payout" value="0">
  <label>Страна</label><input class="form-control" name="country">
</div><div class="col">
  <label>Лендинг по умолч.</label><select class="form-select" name="default_lander_id"><option value="">--</option>{% for l in landers %}<option value="{{l[0]}}">{{l[1]}}</option>{% endfor %}</select>
  <label>Партнёрка</label><select class="form-select" name="network_id"><option value="">--</option>{% for n in networks %}<option value="{{n[0]}}">{{n[1]}}</option>{% endfor %}</select>
</div></div></div><div class="modal-footer"><button class="btn btn-primary">Создать</button></div></form></div></div>

<script>
  // --- Массовые действия ---
  function toggleAllOffer(source) {
    document.querySelectorAll('.bulk-check-offer').forEach(cb => cb.checked = source.checked);
    updateBulkPanelOffer();
  }

  function updateBulkPanelOffer() {
    const checked = document.querySelectorAll('.bulk-check-offer:checked');
    const count = checked.length;
    document.getElementById('selected-count-offers').textContent = count;
    document.getElementById('bulk-actions-offers').style.display = count > 0 ? 'block' : 'none';
  }

  function getSelectedIdsOffer() {
    return Array.from(document.querySelectorAll('.bulk-check-offer:checked')).map(cb => cb.value);
  }

  function clearBulkSelectionOffer() {
    document.querySelectorAll('.bulk-check-offer').forEach(cb => cb.checked = false);
    document.getElementById('select-all-offers').checked = false;
    updateBulkPanelOffer();
  }

  async function bulkActionOffer(action) {
    const ids = getSelectedIdsOffer();
    if (ids.length === 0) { alert('Не выбраны элементы'); return; }

    if (action === 'set_group_prompt') {
      new bootstrap.Modal(document.getElementById('bulkGroupModalOffer')).show();
      return;
    }
    if (action === 'set_tags_prompt') {
      new bootstrap.Modal(document.getElementById('bulkTagsModalOffer')).show();
      return;
    }

    const resp = await fetch('/offers/bulk-action', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ action, ids })
    });
    const data = await resp.json();
    if (data.success) { location.reload(); }
    else { alert('Ошибка: ' + (data.error || 'неизвестно')); }
  }

  async function executeBulkGroupOffer() {
    const ids = getSelectedIdsOffer();
    const group_id = document.getElementById('bulk_group_select_offer').value || null;
    const resp = await fetch('/offers/bulk-action', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ action: 'set_group', ids, group_id })
    });
    const data = await resp.json();
    if (data.success) { location.reload(); }
    else { alert('Ошибка: ' + (data.error || 'неизвестно')); }
  }

  async function executeBulkTagsOffer() {
    const ids = getSelectedIdsOffer();
    const mode = document.querySelector('input[name="bulk_tag_mode_offer"]:checked').value;
    const tags = document.querySelector('#bulkTagsModalOffer input[name="tags"]').value;
    const resp = await fetch('/offers/bulk-action', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ action: 'set_tags', ids, tags, tag_mode: mode })
    });
    const data = await resp.json();
    if (data.success) { location.reload(); }
    else { alert('Ошибка: ' + (data.error || 'неизвестно')); }
  }
</script>
''' + FOOTER

CLICKLOG_HTML = HEADER + '''
<h4>Клик-лог
  <button class="btn btn-sm btn-info float-end ms-1" onclick="openIpExportModal()">📥 IP адреса</button>
  <a class="btn btn-sm btn-info float-end ms-1" href="/clicklog/export?{{ request.query_string.decode() }}">📥 Скачать CSV</a>
</h4>

<!-- Поиск -->
<form class="row g-2 mb-3" method="get">
  <div class="col-auto">
    <input class="form-control form-control-sm" name="q" placeholder="Поиск по Click ID (внутр./внеш.)" value="{{ search_q }}">
  </div>
  <div class="col-auto">
    <input class="form-control form-control-sm" name="ip" placeholder="Поиск по IP" value="{{ search_ip }}">
  </div>
  <div class="col-auto">
    <button class="btn btn-sm btn-outline-warning">Искать</button>
    <a href="/clicklog" class="btn btn-sm btn-outline-secondary">Сброс</a>
  </div>
</form>

<!-- Панель управления колонками -->
<div class="mb-3 p-2 bg-dark rounded" style="font-size:0.8rem;">
  <span class="text-warning me-2">🎛️ Колонки:</span>
  <label class="me-2"><input type="checkbox" class="col-toggle" data-col="0" checked> Кампания</label>
  <label class="me-2"><input type="checkbox" class="col-toggle" data-col="1" checked> Лендинг</label>
  <label class="me-2"><input type="checkbox" class="col-toggle" data-col="2" checked> Оффер</label>
  <label class="me-2"><input type="checkbox" class="col-toggle" data-col="3" checked> Click ID</label>
  <label class="me-2"><input type="checkbox" class="col-toggle" data-col="4" checked> External ID</label>
  <label class="me-2"><input type="checkbox" class="col-toggle" data-col="5" checked> IP</label>
  <label class="me-2"><input type="checkbox" class="col-toggle" data-col="6" checked> User-Agent</label>
  <label class="me-2"><input type="checkbox" class="col-toggle" data-col="7" checked> Страна</label>
  <label class="me-2"><input type="checkbox" class="col-toggle" data-col="8" checked> Город</label>
  <label class="me-2"><input type="checkbox" class="col-toggle" data-col="9" checked> Время клика</label>
  <label class="me-2"><input type="checkbox" class="col-toggle" data-col="10" checked> Выплата</label>
  <label class="me-2"><input type="checkbox" class="col-toggle" data-col="11"> Sub1</label>
  <label class="me-2"><input type="checkbox" class="col-toggle" data-col="12"> Sub2</label>
  <label class="me-2"><input type="checkbox" class="col-toggle" data-col="13"> Sub3</label>
  <label class="me-2"><input type="checkbox" class="col-toggle" data-col="14"> Sub4</label>
  <label class="me-2"><input type="checkbox" class="col-toggle" data-col="15"> Sub5</label>
  <label class="me-2"><input type="checkbox" class="col-toggle" data-col="16"> Sub6</label>
  <label class="me-2"><input type="checkbox" class="col-toggle" data-col="17"> Sub7</label>
  <label class="me-2"><input type="checkbox" class="col-toggle" data-col="18"> Sub8</label>
  <label class="me-2"><input type="checkbox" class="col-toggle" data-col="19"> Sub9</label>
  <label class="me-2"><input type="checkbox" class="col-toggle" data-col="20"> Sub10</label>
  <label class="me-2"><input type="checkbox" class="col-toggle" data-col="21"> Sub11</label>
</div>

<div class="table-responsive">
<table class="table table-sm table-hover" id="clicklog-table">
<thead>
  <tr>
    <th>Кампания</th>
    <th>Лендинг</th>
    <th>Оффер</th>
    <th>Click ID</th>
    <th>External ID</th>
    <th>IP</th>
    <th>User-Agent</th>
    <th>Страна</th>
    <th>Город</th>
    <th>Время клика</th>
    <th>Выплата</th>
    <th>Sub1</th><th>Sub2</th><th>Sub3</th><th>Sub4</th><th>Sub5</th>
    <th>Sub6</th><th>Sub7</th><th>Sub8</th><th>Sub9</th><th>Sub10</th><th>Sub11</th>
  </tr>
</thead>
<tbody>
{% for r in rows %}
<tr>
  <td>{{r[0]}}</td>
  <td>{{r[1]}}</td>
  <td>{{r[2]}}</td>
  <td><code>{{r[3]}}</code></td>
  <td><code>{{r[10] or '—'}}</code></td>
  <td>{{r[4]}}</td>
  <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;">{{r[5]}}</td>
  <td>{{r[6] or '-'}}</td>
  <td>{{r[7] or '-'}}</td>
  <td>{{r[8]}}</td>
  <td>{{"$%.2f"|format(r[9]) if r[9] else '-'}}</td>
  <td>{{r[11] or '—'}}</td><td>{{r[12] or '—'}}</td><td>{{r[13] or '—'}}</td>
  <td>{{r[14] or '—'}}</td><td>{{r[15] or '—'}}</td><td>{{r[16] or '—'}}</td>
  <td>{{r[17] or '—'}}</td><td>{{r[18] or '—'}}</td><td>{{r[19] or '—'}}</td>
  <td>{{r[20] or '—'}}</td><td>{{r[21] or '—'}}</td>
</tr>
{% endfor %}
</tbody>
</table>
</div>
<nav><ul class="pagination">{% for p in range(1,total_pages+1) %}<li class="page-item {{'active' if p==page}}"><a class="page-link" href="?page={{p}}&q={{ search_q }}&ip={{ search_ip }}">{{p}}</a></li>{% endfor %}</ul></nav>

<!-- Модалка для экспорта IP -->
<div class="modal fade" id="ipExportModal" tabindex="-1">
  <div class="modal-dialog">
    <div class="modal-content bg-dark text-light">
      <div class="modal-header">
        <h5>Скачать IP адреса</h5>
        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        <label class="form-label">Кампания</label>
        <select class="form-select" id="ipCampaignSelect">
          <option value="all">Все кампании</option>
          {% for c in campaigns %}
            <option value="{{ c[0] }}">{{ c[1] }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-primary" onclick="downloadIps()">Скачать</button>
      </div>
    </div>
  </div>
</div>

<script>
// Сохранение и восстановление видимости колонок
(function() {
  const table = document.getElementById('clicklog-table');
  const toggles = document.querySelectorAll('.col-toggle');
  
  const saved = JSON.parse(localStorage.getItem('clicklogColumns') || '{}');
  toggles.forEach(cb => {
    const col = cb.dataset.col;
    if (saved.hasOwnProperty(col)) {
      cb.checked = saved[col];
    }
    applyVisibility(col, cb.checked);
  });
  
  toggles.forEach(cb => {
    cb.addEventListener('change', function() {
      const col = this.dataset.col;
      applyVisibility(col, this.checked);
      const current = JSON.parse(localStorage.getItem('clicklogColumns') || '{}');
      current[col] = this.checked;
      localStorage.setItem('clicklogColumns', JSON.stringify(current));
    });
  });
  
  function applyVisibility(colIndex, visible) {
    const th = table.querySelectorAll('thead th')[colIndex];
    if (th) th.style.display = visible ? '' : 'none';
    table.querySelectorAll('tbody tr').forEach(tr => {
      const td = tr.querySelectorAll('td')[colIndex];
      if (td) td.style.display = visible ? '' : 'none';
    });
  }
})();

// Открыть модалку экспорта IP
function openIpExportModal() {
  new bootstrap.Modal(document.getElementById('ipExportModal')).show();
}

// Скачать IP
function downloadIps() {
  const campaignId = document.getElementById('ipCampaignSelect').value;
  const url = '/clicklog/export-ips?campaign_id=' + encodeURIComponent(campaignId);
  window.location.href = url;
}
</script>
''' + FOOTER

# ====== СТАРЫЕ ШАБЛОНЫ (без изменений) ======
SERVER_STATUS_HTML = HEADER + '''
<h4>Состояние сервера</h4>
<table class="table table-striped"><tbody>
<tr><td>CPU</td><td>{{ cpu }}%</td></tr>
<tr><td>RAM</td><td>{{ mem.used // 1024**2 }} MB / {{ mem.total // 1024**2 }} MB ({{ mem.percent }}%)</td></tr>
<tr><td>Диск</td><td>{{ disk.used // 1024**3 }} GB / {{ disk.total // 1024**3 }} GB ({{ disk.percent }}%)</td></tr>
<tr><td>Нагрузка</td><td>{{ "%.2f %.2f %.2f"|format(load[0], load[1], load[2]) }}</td></tr>
<tr><td>Аптайм</td><td>{{ uptime_str }}</td></tr>
</tbody></table><meta http-equiv="refresh" content="2">''' + FOOTER

USERS_HTML = HEADER + '''
<h4>Пользователи <button class="btn btn-primary btn-sm float-end" data-bs-toggle="modal" data-bs-target="#createUserModal">Создать</button></h4>
<table class="table table-striped table-hover"><thead><tr><th>ID</th><th>Логин</th><th>Роль</th><th></th></tr></thead><tbody>
{% for u in users %}<tr><td>{{u[0]}}</td><td>{{u[1]}}</td><td>{{u[2]}}</td><td>
<button class="btn btn-sm btn-warning" data-bs-toggle="modal" data-bs-target="#editUserModal{{u[0]}}">✎</button>
<form method="post" action="/admin/user/delete/{{u[0]}}" style="display:inline"><button class="btn btn-sm btn-danger">🗑</button></form>
</td></tr>{% endfor %}</tbody></table>

{% for u in users %}
<div class="modal fade" id="editUserModal{{u[0]}}" tabindex="-1"><div class="modal-dialog"><form class="modal-content" method="post" action="/admin/user/edit/{{u[0]}}"><div class="modal-header"><h5>Редактировать пользователя</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div><div class="modal-body">
<label>Логин</label><input class="form-control" name="username" value="{{u[1]}}" required>
<label>Новый пароль</label><input class="form-control" name="password" type="password" placeholder="Оставьте пустым">
<label>Роль</label><select class="form-select" name="role"><option value="admin" {{'selected' if u[2]=='admin'}}>Админ</option><option value="manager" {{'selected' if u[2]=='manager'}}>Менеджер</option><option value="guest" {{'selected' if u[2]=='guest'}}>Гость</option></select>
</div><div class="modal-footer"><button class="btn btn-primary">Сохранить</button></div></form></div></div>
{% endfor %}

<div class="modal fade" id="createUserModal" tabindex="-1"><div class="modal-dialog"><form class="modal-content" method="post" action="/admin/user/create"><div class="modal-header"><h5>Новый пользователь</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div><div class="modal-body">
<label>Логин</label><input class="form-control" name="username" required><label>Пароль</label><input class="form-control" name="password" type="password" required>
<label>Роль</label><select class="form-select" name="role"><option value="admin">Админ</option><option value="manager">Менеджер</option><option value="guest">Гость</option></select>
</div><div class="modal-footer"><button class="btn btn-primary">Создать</button></div></form></div></div>''' + FOOTER

SOURCES_HTML = HEADER + '''<h4>Источники трафика <button class="btn btn-primary btn-sm float-end" data-bs-toggle="modal" data-bs-target="#createSourceModal">Создать</button></h4>
<!-- Панель периода и экспорта -->
<form class="row g-2 mb-3" method="get" id="periodForm">
  <div class="col-auto">
    <select class="form-select form-select-sm" name="period" onchange="handlePeriodChange(this.value)">
      <option value="all" {{ 'selected' if period=='all' else '' }}>Всё время</option>
      <option value="today" {{ 'selected' if period=='today' else '' }}>Сегодня</option>
      <option value="yesterday" {{ 'selected' if period=='yesterday' else '' }}>Вчера</option>
      <option value="3days" {{ 'selected' if period=='3days' else '' }}>3 дня</option>
      <option value="week" {{ 'selected' if period=='week' else '' }}>Неделя</option>
      <option value="2weeks" {{ 'selected' if period=='2weeks' else '' }}>2 недели</option>
      <option value="month" {{ 'selected' if period=='month' else '' }}>Месяц</option>
      <option value="year" {{ 'selected' if period=='year' else '' }}>Год</option>
      <option value="custom" {{ 'selected' if period=='custom' else '' }}>Произвольный</option>
    </select>
  </div>
  <div class="col-auto" id="customDateFields" style="display: {{ 'block' if period=='custom' else 'none' }};">
    <input type="date" class="form-control form-control-sm d-inline w-auto" name="start" value="{{ start }}">
    <span class="text-light">—</span>
    <input type="date" class="form-control form-control-sm d-inline w-auto" name="end" value="{{ end }}">
  </div>
  <div class="col-auto">
    <button type="submit" class="btn btn-sm btn-outline-warning">Применить</button>
    <a href="/traffic-sources/export-csv?{{ request.query_string.decode() }}" class="btn btn-sm btn-info">📥 CSV</a>
  </div>
</form>
<script>
function handlePeriodChange(val) {
  document.getElementById('customDateFields').style.display = val === 'custom' ? 'block' : 'none';
  if (val !== 'custom') document.getElementById('periodForm').submit();
}
</script>
<div class="table-responsive">
<table class="table table-striped table-hover"><thead><tr>
  <th>ID</th><th>Название</th><th>Тип</th>
  <th>Клики</th><th>Лиды</th><th>Аппрув</th><th>Аппрув-рейт</th>
  <th>Доход</th><th>Расход</th><th>Прибыль</th><th>ROI</th>
  <th>CPC</th><th>EPC</th><th>CR</th><th></th>
</tr></thead><tbody>
{% for s in sources %}{% set st = stats[s[0]] %}
{% set profit = st.revenue - st.cost %}
<tr>
  <td>{{s[0]}}</td><td>{{s[1]}}</td><td>{{s[2]}}</td>
  <td>{{st.clicks}}</td>
  <td>{{st.leads}}</td>
  <td>{{st.approved}}</td>
  <td>{{ "%.1f"|format((st.approved/st.leads*100) if st.leads>0 else 0) }}%</td>
  <td>${{"%.2f"|format(st.revenue)}}</td>
  <td>${{"%.4f"|format(st.cost)}}</td>
  <td>${{"%.2f"|format(profit)}}</td>
  <td>{{"%.1f"|format((profit/st.cost*100) if st.cost>0 else 0)}}%</td>
  <td>${{"%.4f"|format((st.cost/st.clicks) if st.clicks>0 else 0)}}</td>
  <td>${{"%.4f"|format((st.revenue/st.clicks) if st.clicks>0 else 0)}}</td>
  <td>{{"%.2f"|format((st.leads/st.clicks*100) if st.clicks>0 else 0)}}%</td>
  <td>
    <button class="btn btn-sm btn-warning" data-bs-toggle="modal" data-bs-target="#editSourceModal{{s[0]}}">✎</button>
    <form method="post" action="/traffic-source/delete/{{s[0]}}" style="display:inline"><button class="btn btn-sm btn-danger">🗑</button></form>
  </td>
</tr>
{% endfor %}</tbody></table>
</div>

<!-- Модалки редактирования -->
{% for s in sources %}
<div class="modal fade" id="editSourceModal{{s[0]}}" tabindex="-1"><div class="modal-dialog"><div class="modal-content bg-dark text-light"><div class="modal-header"><h5>Редактировать источник</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div><form method="post" action="/traffic-source/edit/{{s[0]}}"><div class="modal-body">
<label>Название</label><input class="form-control" name="name" value="{{s[1]}}" required>
<label>S2S Postback URL</label>
<div class="input-group input-group-sm">
  <select class="form-select" id="s2s_template_select_{{s[0]}}" onchange="fillS2SUrl(this, 's2s_url_{{s[0]}}')">
    <option value="">-- Выбрать шаблон --</option>
    {% for name, tpl in s2s_templates.items() %}
      {% if tpl.s2s_postback_url %}
        <option value="{{ tpl.s2s_postback_url }}">{{ name }}</option>
      {% endif %}
    {% endfor %}
  </select>
  <button type="button" class="btn btn-sm btn-outline-warning" onclick="clearS2S('s2s_url_{{s[0]}}')">✕</button>
</div>
<input type="text" class="form-control mt-2" name="s2s_postback_url" id="s2s_url_{{s[0]}}" value="{{s[3] if s[3] else ''}}" placeholder="Или введите URL вручную">
</div><div class="modal-footer"><button type="submit" class="btn btn-primary">Сохранить</button></div></form></div></div></div>
{% endfor %}

<!-- Модалка создания (ОДНА, вне цикла) -->
<div class="modal fade" id="createSourceModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content bg-dark text-light"><div class="modal-header"><h5>Новый источник</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div><form method="post" action="/traffic-source/create"><div class="modal-body">
<label>Название</label><input class="form-control" name="name" required>
<label>S2S Postback URL</label>
<div class="input-group input-group-sm">
  <select class="form-select" id="s2s_template_select_new" onchange="fillS2SUrl(this, 's2s_url_new')">
    <option value="">-- Выбрать шаблон --</option>
    {% for name, tpl in s2s_templates.items() %}
      {% if tpl.s2s_postback_url %}
        <option value="{{ tpl.s2s_postback_url }}">{{ name }}</option>
      {% endif %}
    {% endfor %}
  </select>
  <button type="button" class="btn btn-sm btn-outline-warning" onclick="clearS2S('s2s_url_new')">✕</button>
</div>
<input type="text" class="form-control mt-2" name="s2s_postback_url" id="s2s_url_new" placeholder="Или введите URL вручную">
</div><div class="modal-footer"><button type="submit" class="btn btn-primary">Создать</button></div></form></div></div>

<script>
const currentDomain = "{{ DOMAIN }}";

function fillS2SUrl(select, targetId) {
  const url = select.value;
  if (url) {
    document.getElementById(targetId).value = url.replace('{host}', currentDomain);
  }
}

function clearS2S(targetId) {
  document.getElementById(targetId).value = '';
  // Сбросить выпадающий список
  const select = document.querySelector(`[onchange="fillS2SUrl(this, '${targetId}')"]`);
  if (select) select.value = '';
}
</script>
''' + FOOTER

AFFILIATE_HTML = HEADER + '''<h4>Партнёрские сети <button class="btn btn-primary btn-sm float-end" data-bs-toggle="modal" data-bs-target="#createAffModal">Создать</button></h4><!-- Панель периода и экспорта -->
<form class="row g-2 mb-3" method="get" id="periodForm">
  <div class="col-auto">
    <select class="form-select form-select-sm" name="period" onchange="handlePeriodChange(this.value)">
      <option value="all" {{ 'selected' if period=='all' else '' }}>Всё время</option>
      <option value="today" {{ 'selected' if period=='today' else '' }}>Сегодня</option>
      <option value="yesterday" {{ 'selected' if period=='yesterday' else '' }}>Вчера</option>
      <option value="3days" {{ 'selected' if period=='3days' else '' }}>3 дня</option>
      <option value="week" {{ 'selected' if period=='week' else '' }}>Неделя</option>
      <option value="2weeks" {{ 'selected' if period=='2weeks' else '' }}>2 недели</option>
      <option value="month" {{ 'selected' if period=='month' else '' }}>Месяц</option>
      <option value="year" {{ 'selected' if period=='year' else '' }}>Год</option>
      <option value="custom" {{ 'selected' if period=='custom' else '' }}>Произвольный</option>
    </select>
  </div>
  <div class="col-auto" id="customDateFields" style="display: {{ 'block' if period=='custom' else 'none' }};">
    <input type="date" class="form-control form-control-sm d-inline w-auto" name="start" value="{{ start }}">
    <span class="text-light">—</span>
    <input type="date" class="form-control form-control-sm d-inline w-auto" name="end" value="{{ end }}">
  </div>
  <div class="col-auto">
    <button type="submit" class="btn btn-sm btn-outline-warning">Применить</button>
    <a href="/affiliate-networks/export-csv?{{ request.query_string.decode() }}" class="btn btn-sm btn-info">📥 CSV</a>
  </div>
</form>
<script>
function handlePeriodChange(val) {
  document.getElementById('customDateFields').style.display = val === 'custom' ? 'block' : 'none';
  if (val !== 'custom') document.getElementById('periodForm').submit();
}
</script>
<div class="table-responsive">
<table class="table table-striped table-hover"><thead><tr>
  <th>ID</th><th>Название</th>
  <th>Клики</th><th>Лиды</th><th>Аппрув</th><th>Аппрув-рейт</th>
  <th>Доход</th><th>Расход</th><th>Прибыль</th><th>ROI</th>
  <th>CPC</th><th>EPC</th><th>CR</th><th></th>
</tr></thead><tbody>
{% for n in networks %}{% set ns = stats[n[0]] %}
{% set profit = ns.revenue - ns.cost %}
<tr>
  <td>{{n[0]}}</td><td>{{n[1]}}</td>
  <td>{{ns.clicks}}</td>
  <td>{{ns.leads}}</td>
  <td>{{ns.approved}}</td>
  <td>{{ "%.1f"|format((ns.approved/ns.leads*100) if ns.leads>0 else 0) }}%</td>
  <td>${{"%.2f"|format(ns.revenue)}}</td>
  <td>${{"%.4f"|format(ns.cost)}}</td>
  <td>${{"%.2f"|format(profit)}}</td>
  <td>{{"%.1f"|format((profit/ns.cost*100) if ns.cost>0 else 0)}}%</td>
  <td>${{"%.4f"|format((ns.cost/ns.clicks) if ns.clicks>0 else 0)}}</td>
  <td>${{"%.4f"|format((ns.revenue/ns.clicks) if ns.clicks>0 else 0)}}</td>
  <td>{{"%.2f"|format((ns.leads/ns.clicks*100) if ns.clicks>0 else 0)}}%</td>
  <td>
    <button class="btn btn-sm btn-warning" data-bs-toggle="modal" data-bs-target="#editAffModal{{n[0]}}">✎</button>
    <form method="post" action="/affiliate-network/delete/{{n[0]}}" style="display:inline"><button class="btn btn-sm btn-danger">🗑</button></form>
  </td>
</tr>
{% endfor %}</tbody></table>
</div>

{% for n in networks %}
<div class="modal fade" id="editAffModal{{n[0]}}" tabindex="-1"><div class="modal-dialog"><div class="modal-content bg-dark text-light"><div class="modal-header"><h5>Редактировать партнёрскую сеть</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div><div class="modal-body"><label>Название</label><input class="form-control" name="name" value="{{n[1]}}" required><label>Шаблон URL клика</label><input class="form-control" name="url_template" value="{{n[2]}}"><label>URL постбека</label><input class="form-control" name="postback_url_template" value="{{n[3]}}"><div class="mt-2"><button type="button" class="btn btn-sm btn-outline-warning" onclick="showTemplates('edit')">📋 Шаблоны</button></div></div><div class="modal-footer"><button class="btn btn-primary">Сохранить</button></div></div></div></div>
{% endfor %}

<div class="modal fade" id="createAffModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content bg-dark text-light"><div class="modal-header"><h5>Новая партнёрская сеть</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div><div class="modal-body"><label>Название</label><input class="form-control" name="name" required><label>Шаблон URL клика</label><input class="form-control" name="url_template" placeholder="{offer_url}?sub1={click_id}"><label>URL постбека</label><input class="form-control" name="postback_url_template" placeholder="http://{host}/postback?click_id={sub1}&payout={payment}"><div class="mt-2"><button type="button" class="btn btn-sm btn-outline-warning" onclick="showTemplates('create')">📋 Шаблоны</button></div></div><div class="modal-footer"><button class="btn btn-primary">Создать</button></div></div></div></div>

<div class="modal fade" id="templatesModal" tabindex="-1"><div class="modal-dialog modal-lg"><div class="modal-content bg-dark text-light"><div class="modal-header"><h5>Шаблоны партнёрских сетей</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div><div class="modal-body"><div class="list-group">{% for name, tpl in templates.items() %}<a href="#" class="list-group-item list-group-item-action bg-secondary text-light" onclick="fillFromTemplate('{{name}}')">{{name}}</a>{% endfor %}</div></div></div></div></div>
<script>
const templates = {{ templates|tojson|safe }};
let activeForm = 'create';
function showTemplates(formType) {
  activeForm = formType;
  new bootstrap.Modal(document.getElementById('templatesModal')).show();
}
function fillFromTemplate(name) {
  const tpl = templates[name];
  if (!tpl) return;
  const modal = document.getElementById(activeForm === 'create' ? 'createAffModal' : 'editAffModal');
  if (!modal) return;
  // Название сети
  modal.querySelector('input[name="name"]').value = name;
  // Шаблоны, заменяем {host} на чистый домен
  modal.querySelector('input[name="url_template"]').value = tpl.url_template.replace('{host}', '{{ DOMAIN }}');
  modal.querySelector('input[name="postback_url_template"]').value = tpl.postback_template.replace('{host}', '{{ DOMAIN }}');
  bootstrap.Modal.getInstance(document.getElementById('templatesModal')).hide();
}
</script>
''' + FOOTER

GROUPS_HTML = HEADER + '''<h4>Группы <button class="btn btn-primary btn-sm float-end" data-bs-toggle="modal" data-bs-target="#createGroupModal">Создать</button></h4>
<table class="table table-striped table-hover"><thead><tr><th>ID</th><th>Название</th><th>Лендингов</th><th>Офферов</th><th></th></tr></thead><tbody>
{% for g in groups %}
<tr>
  <td>{{g[0]}}</td>
  <td>{{g[1]}}</td>
  <td>{{g[2]}}</td>
  <td>{{g[3]}}</td>
  <td>
    <button class="btn btn-sm btn-warning" data-bs-toggle="modal" data-bs-target="#editGroupModal{{g[0]}}">✎</button>
    <form method="post" action="/group/delete/{{g[0]}}" style="display:inline"><button class="btn btn-sm btn-danger">🗑</button></form>
  </td>
</tr>
{% endfor %}</tbody></table>

{% for g in groups %}
<div class="modal fade" id="editGroupModal{{g[0]}}" tabindex="-1"><div class="modal-dialog"><form class="modal-content" method="post" action="/group/edit/{{g[0]}}"><div class="modal-header"><h5>Редактировать группу</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div><div class="modal-body"><label>Название</label><input class="form-control" name="name" value="{{g[1]}}" required></div><div class="modal-footer"><button class="btn btn-primary">Сохранить</button></div></form></div></div>
{% endfor %}

<div class="modal fade" id="createGroupModal" tabindex="-1"><div class="modal-dialog"><form class="modal-content" method="post" action="/group/create"><div class="modal-header"><h5>Новая группа</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div><div class="modal-body"><label>Название</label><input class="form-control" name="name" required></div><div class="modal-footer"><button class="btn btn-primary">Создать</button></div></form></div></div>''' + FOOTER

CHALLENGE_HTML = '''
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Проверка...</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: radial-gradient(ellipse at 50% 30%, #1a2f3f 0%, #0a1622 100%);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: 'Georgia', serif;
      overflow: hidden;
      position: relative;
    }
    /* Звёзды */
    .stars {
      position: absolute;
      top: 0; left: 0; right: 0; bottom: 0;
      background: transparent;
      background-image:
        radial-gradient(1px 1px at 10% 15%, rgba(255,255,240,0.8), transparent),
        radial-gradient(1px 1px at 25% 35%, rgba(255,255,240,0.6), transparent),
        radial-gradient(1px 1px at 40% 8%, rgba(255,255,240,0.7), transparent),
        radial-gradient(1px 1px at 55% 25%, rgba(255,255,240,0.5), transparent),
        radial-gradient(1px 1px at 70% 12%, rgba(255,255,240,0.9), transparent),
        radial-gradient(1px 1px at 85% 22%, rgba(255,255,240,0.6), transparent),
        radial-gradient(1px 1px at 15% 45%, rgba(255,255,240,0.4), transparent),
        radial-gradient(1px 1px at 60% 40%, rgba(255,255,240,0.7), transparent),
        radial-gradient(1px 1px at 92% 38%, rgba(255,255,240,0.5), transparent);
      animation: twinkle 4s infinite alternate;
    }
    @keyframes twinkle {
      0% { opacity: 0.4; }
      100% { opacity: 0.9; }
    }
    /* Корабль */
    .ship {
      position: relative;
      width: 200px;
      height: 250px;
      z-index: 10;
      animation: float 6s ease-in-out infinite;
    }
    @keyframes float {
      0% { transform: translateY(0) rotate(-1deg); }
      50% { transform: translateY(-15px) rotate(1deg); }
      100% { transform: translateY(0) rotate(-1deg); }
    }
    .ship-body {
      position: absolute;
      bottom: 0;
      left: 50%;
      transform: translateX(-50%);
      width: 160px;
      height: 60px;
      background: linear-gradient(to bottom, #5c3a1e, #3b2410);
      border-radius: 10px 10px 30px 30px;
      box-shadow: 0 10px 20px rgba(0,0,0,0.5);
    }
    .ship-body::after {
      content: '';
      position: absolute;
      top: -20px;
      left: 30px;
      right: 30px;
      height: 20px;
      background: #7a4f28;
      border-radius: 5px 5px 0 0;
    }
    .mast {
      position: absolute;
      bottom: 60px;
      left: 50%;
      transform: translateX(-50%);
      width: 6px;
      height: 120px;
      background: #4a3018;
    }
    .sail {
      position: absolute;
      bottom: 100px;
      left: 50%;
      transform: translateX(-50%);
      width: 100px;
      height: 70px;
      background: #e0d7c6;
      clip-path: polygon(0 0, 100% 50%, 0 100%);
      opacity: 0.85;
    }
    .flag {
      position: absolute;
      top: 5px;
      left: -3px;
      width: 0;
      height: 0;
      border-left: 20px solid #e74c3c;
      border-top: 12px solid transparent;
      border-bottom: 12px solid transparent;
    }
    /* Штурвал */
    .wheel-container {
      position: absolute;
      bottom: 20px;
      right: 20px;
      width: 80px;
      height: 80px;
      opacity: 0.3;
      animation: spin 20s linear infinite;
    }
    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
    /* Прогресс-бар */
    .progress-wrap {
      position: absolute;
      bottom: 50px;
      left: 50%;
      transform: translateX(-50%);
      width: 280px;
      height: 4px;
      background: rgba(255,255,255,0.15);
      border-radius: 2px;
      z-index: 20;
      overflow: hidden;
    }
    .progress-fill {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, #e2a03f, #ffcc00);
      box-shadow: 0 0 8px rgba(226,160,63,0.6);
      animation: fill 2s ease-out forwards;
    }
    @keyframes fill {
      0% { width: 0%; }
      100% { width: 90%; }
    }
  </style>
</head>
<body>
  <div class="stars"></div>

  <div class="ship">
    <div class="flag"></div>
    <div class="mast">
      <div class="sail"></div>
    </div>
    <div class="ship-body"></div>
  </div>

  <div class="wheel-container">
    <svg viewBox="0 0 100 100" width="80" height="80">
      <circle cx="50" cy="50" r="45" fill="none" stroke="#8b5a2b" stroke-width="4"/>
      <circle cx="50" cy="50" r="15" fill="none" stroke="#8b5a2b" stroke-width="4"/>
      <line x1="50" y1="5" x2="50" y2="95" stroke="#8b5a2b" stroke-width="4"/>
      <line x1="5" y1="50" x2="95" y2="50" stroke="#8b5a2b" stroke-width="4"/>
      <line x1="12" y1="12" x2="88" y2="88" stroke="#8b5a2b" stroke-width="4"/>
      <line x1="88" y1="12" x2="12" y2="88" stroke="#8b5a2b" stroke-width="4"/>
    </svg>
  </div>

  <div class="progress-wrap">
    <div class="progress-fill"></div>
  </div>

  <form id="challengeForm" method="post" action="/verify-challenge" style="display:none;">
    <input type="hidden" name="click_id" value="{{ click_id }}">
    <input type="hidden" name="lander_url" value="{{ lander_url }}">
    <input type="hidden" name="expected" value="{{ expected }}">
    <input type="hidden" name="answer" id="answerInput">
  </form>

  <script>
    setTimeout(() => {
      document.getElementById('answerInput').value = eval("{{ challenge }}");
      document.getElementById('challengeForm').submit();
    }, 2000);
  </script>
</body>
</html>
'''

CAMPAIGN_NEW_HTML = HEADER + '''
<h4>Новая кампания</h4>

<script>
// Глобальные списки для динамических путей и правил
window.landers = {{ landers|tojson|safe }};
window.offers = {{ offers|tojson|safe }};
window.COUNTRY_CODES = {{ COUNTRY_CODES|tojson|safe }};
</script>

<form method="post" id="campaignForm">

  <!-- ====== БЛОК 1: ОСНОВНЫЕ НАСТРОЙКИ ====== -->
  <div class="card bg-dark mb-3">
    <div class="card-header">Основные настройки</div>
    <div class="card-body">
      <div class="row mb-3">
        <div class="col-md-6">
          <label class="form-label">Название кампании</label>
          <input class="form-control" name="name" required>
        </div>
        <div class="col-md-6">
          <label class="form-label">Домен</label>
          <select class="form-select" name="domain_id">
            <option value="">-- По умолчанию --</option>
            {% for d in domains %}<option value="{{d[0]}}">{{d[1]}}</option>{% endfor %}
          </select>
        </div>
        <div class="col-md-4">
          <label class="form-label">Группа</label>
          <div class="input-group input-group-sm">
             <select class="form-select" name="group_id" id="group_select_new_campaign">
              <option value="">-- Без группы --</option>
              {% for g in groups %}<option value="{{g[0]}}">{{g[1]}}</option>{% endfor %}
            </select>
            <button type="button" class="btn btn-sm btn-outline-warning" onclick="createGroup(document.getElementById('group_select_new_campaign'))">+</button>
          </div>
        </div>
      </div>

      <div class="row mb-3">
        <div class="col-md-4">
          <label class="form-label">Лендинг по умолчанию</label>
          <select class="form-select" name="lander_id">
            <option value="">-- Не выбран --</option>
            {% for l in landers %}<option value="{{l[0]}}">{{l[1]}}</option>{% endfor %}
          </select>
        </div>
        <div class="col-md-4">
          <label class="form-label">Оффер по умолчанию</label>
          <select class="form-select" name="offer_id">
            <option value="">-- Не выбран --</option>
            {% for o in offers %}<option value="{{o[0]}}">{{o[1]}}</option>{% endfor %}
          </select>
        </div>
        <div class="col-md-4">
          <label class="form-label">Источник трафика</label>
          <select class="form-select" name="source_id">
            <option value="">-- Не выбран --</option>
            {% for s in sources %}<option value="{{s[0]}}">{{s[1]}}</option>{% endfor %}
          </select>
        </div>
      </div>

      <div class="row mb-3">
        <div class="col-md-4">
          <label class="form-label">Партнёрская сеть</label>
          <select class="form-select" name="network_id">
            <option value="">-- Не выбрана --</option>
            {% for n in networks %}<option value="{{n[0]}}">{{n[1]}}</option>{% endfor %}
          </select>
        </div>
        <div class="col-md-4">
          <label class="form-label">JS-челлендж</label>
          <div class="form-check">
            <input class="form-check-input" type="checkbox" name="js_challenge_enabled" id="jsChallenge">
            <label class="form-check-label" for="jsChallenge">Включить</label>
          </div>
          <select class="form-select form-select-sm mt-1" name="js_challenge_level">
            <option value="super_easy">Супер простой</option>
            <option value="easy" selected>Простой</option>
            <option value="medium">Средний</option>
          </select>
        </div>
        <div class="col-md-4">
          <label class="form-label">S2S постбек URL</label>
          <input class="form-control" name="s2s_postback_url" placeholder="https://...">
        </div>
      </div>
      <!-- Списки IP отдельной строкой -->
      <div class="row mb-3">
        <div class="col-md-12">
          <label class="form-label">Чёрный список IP</label>
          <textarea class="form-control" name="ip_blacklist" rows="2" placeholder="IP через запятую, например: 192.168.1.1, 10.0.0.5"></textarea>
        </div>
        <div class="col-md-12 mt-2">
          <label class="form-label">Белый список IP</label>
          <textarea class="form-control" name="ip_whitelist" rows="2" placeholder="IP через запятую (если задан, только эти IP будут пропущены)"></textarea>
        </div>
      </div>
    </div>
  </div>

  <!-- ====== БЛОК 2: ТЕГИ И СТРАНЫ ====== -->
  <div class="card bg-dark mb-3">
    <div class="card-header">Теги и страны</div>
    <div class="card-body">
      <div class="row">
        <div class="col-md-6">
        <label>Теги</label>
        <div class="tag-picker" data-name="create_tags">
          <div class="selected-tags mb-2"></div>
          <div class="input-group input-group-sm">
            <input type="text" class="form-control tag-search" placeholder="Поиск или новый тег">
            <button type="button" class="btn btn-sm btn-outline-warning tag-create-btn">+ Создать</button>
          </div>
          <div class="tag-dropdown bg-dark p-2 mt-1 rounded" style="max-height:200px;overflow-y:auto;display:none;position:absolute;z-index:1000;width:100%;border:1px solid #e2a03f;">
            {% for tag in AVAILABLE_TAGS %}
              {% set color = TAG_COLOR_MAP.get(tag, '#95a5a6') %}
              <div class="form-check">
                <input class="form-check-input tag-check" type="checkbox" value="{{ tag }}" id="create_tag_{{ tag }}">
                <label class="form-check-label" for="create_tag_{{ tag }}">
                  <span class="badge" style="background-color:{{ color }};margin-right:5px;">&nbsp;</span> {{ tag }}
                </label>
              </div>
            {% endfor %}
          </div>
          <input type="hidden" name="tags" value="">
        </div>
        </div>
        <div class="col-md-6">
          <label class="form-label">Страны</label>
          <div class="country-picker" data-name="countries_json">
            <div class="selected-countries mb-2"></div>
            <input type="text" class="form-control form-control-sm country-search" placeholder="Поиск страны...">
            <div class="country-dropdown bg-dark p-2 mt-1 rounded" style="max-height:200px;overflow-y:auto;display:none;position:absolute;z-index:1000;width:100%;border:1px solid #e2a03f;">
              {% for code, name in COUNTRY_CODES.items() %}
              <div class="form-check">
                <input class="form-check-input country-check" type="checkbox" value="{{ code }}" id="create_country_{{ code }}">
                <label class="form-check-label" for="create_country_{{ code }}">{{ code }} - {{ name }}</label>
              </div>
              {% endfor %}
            </div>
            <select multiple name="countries_json" style="display:none;"></select>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ====== БЛОК 3: ПУТИ И РАСПРЕДЕЛЕНИЕ ТРАФИКА (процентный сплит) ====== -->
  <div class="card bg-dark mb-3">
    <div class="card-header">Пути и распределение трафика (процентный сплит)</div>
    <div class="card-body">
      <div id="pathsContainer"></div>
      <button type="button" class="btn btn-sm btn-success mb-3" onclick="addPath()">➕ Добавить путь</button>
      <div class="mb-3"><strong>Сумма процентов: <span id="percentSum">0</span>%</strong></div>
    </div>
  </div>

  <!-- ====== БЛОК 4: ПРАВИЛА КЛОАКИНГА ====== -->
  <div class="card bg-dark mb-3">
    <div class="card-header">Правила клоакинга</div>
    <div class="card-body">
      <div id="cloakRulesContainer"></div>
      <button type="button" class="btn btn-sm btn-success mb-3" onclick="addCloakRule()">➕ Добавить правило</button>
    </div>
  </div>

  <!-- ====== БЛОК 5: КАСТОМНЫЕ МАКРОСЫ (всегда видно) ====== -->
  <div class="card bg-dark mb-3">
    <div class="card-header">Кастомные макросы</div>
    <div class="card-body">
      <p class="text-muted">Оставьте поле пустым, чтобы использовать стандартное имя параметра.</p>
      <div class="row g-2">
        <div class="col-md-4">
          <label class="form-label">cost</label>
          <input class="form-control form-control-sm" name="macro_cost" placeholder="cost">
        </div>
        <div class="col-md-4">
          <label class="form-label">click_id</label>
          <input class="form-control form-control-sm" name="macro_click_id" placeholder="click_id">
        </div>
        <div class="col-md-4">
          <label class="form-label">payout</label>
          <input class="form-control form-control-sm" name="macro_payout" placeholder="payout">
        </div>
        <div class="col-md-4">
          <label class="form-label">goal</label>
          <input class="form-control form-control-sm" name="macro_goal" placeholder="goal">
        </div>
        {% for i in range(1, 12) %}
        <div class="col-md-4">
          <label class="form-label">sub{{ i }}</label>
          <input class="form-control form-control-sm" name="macro_sub{{ i }}" placeholder="sub{{ i }}">
        </div>
        {% endfor %}
      </div>
    </div>
  </div>

  <div class="mt-4">
    <button type="submit" class="btn btn-primary">Создать кампанию</button>
    <a href="/campaigns" class="btn btn-secondary">Отмена</a>
  </div>
</form>

<script>
// Обработчик отправки формы: добавляем скрытые поля с количеством путей и правил
document.getElementById('campaignForm').addEventListener('submit', function(e) {
    const pathCount = this.querySelectorAll('.path-row').length;
    const ruleCount = this.querySelectorAll('.cloak-rule-row').length;
    const pathInput = document.createElement('input');
    pathInput.type = 'hidden';
    pathInput.name = 'path_count';
    pathInput.value = pathCount;
    this.appendChild(pathInput);

    const ruleInput = document.createElement('input');
    ruleInput.type = 'hidden';
    ruleInput.name = 'rule_count';
    ruleInput.value = ruleCount;
    this.appendChild(ruleInput);
});
</script>
''' + FOOTER

POSTBACK_LOG_EMBED_HTML = '''
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
  body { background-color: #1a1a2e; color: #e0e0e0; font-size: 0.9rem; padding: 10px; }
  .table { background-color: #16213e; color: #e0e0e0; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.4); }
  .table thead { background-color: #0f3460; }
  .table th { color: #e2a03f; font-weight: bold; }
  .table td, .table th { border-color: #2a2a4a; padding: 0.4rem; }
  .btn { font-size: 0.8rem; padding: 3px 8px; }
  .btn-sm { font-size: 0.7rem; padding: 2px 6px; }
  .pagination .page-link { background-color: #16213e; border-color: #2a2a4a; color: #e0e0e0; }
  .pagination .page-item.active .page-link { background-color: #e2a03f; border-color: #e2a03f; color: #000; }
</style>
<h4>📡 Лог постбеков</h4>
<table class="table table-sm table-hover">
<thead>
  <tr>
    <th>ID</th><th>Время</th><th>Click ID</th><th>Выплата</th><th>Статус</th><th>URL</th><th>IP</th><th>Кампания</th><th>Оффер</th><th>Параметры</th>
  </tr>
</thead>
<tbody>
{% for r in rows %}
<tr>
  <td>{{ r[0] }}</td><td>{{ r[1] }}</td><td><code>{{ r[2] }}</code></td><td>${{ "%.2f"|format(r[3]) }}</td><td>{{ r[4] }}</td>
  <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;">{{ r[5] }}</td><td>{{ r[6] }}</td><td>{{ r[7] or '-' }}</td><td>{{ r[8] or '-' }}</td>
  <td>
    {% if r[9] %}
      <button class="btn btn-sm btn-outline-info" onclick="showPostbackParams('{{ r[0] }}')">👁️</button>
      <pre id="pb-params-{{ r[0] }}" style="display:none;">{{ r[9] }}</pre>
    {% else %}—{% endif %}
  </td>
</tr>
{% endfor %}
</tbody>
</table>
<nav><ul class="pagination">{% for p in range(1,total_pages+1) %}<li class="page-item {{'active' if p==page}}"><a class="page-link" href="?page={{p}}&embed=1">{{p}}</a></li>{% endfor %}</ul></nav>

<div class="modal fade" id="pbParamsModal" tabindex="-1">
  <div class="modal-dialog modal-lg"><div class="modal-content bg-dark text-light"><div class="modal-header"><h5>Параметры постбека</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div><div class="modal-body"><pre id="pbParamsContent" style="white-space:pre-wrap;word-break:break-all;"></pre></div></div></div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script>
function showPostbackParams(rowId) {
  const raw = document.getElementById('pb-params-' + rowId).textContent;
  try { const obj = JSON.parse(raw); document.getElementById('pbParamsContent').textContent = JSON.stringify(obj, null, 2); }
  catch(e) { document.getElementById('pbParamsContent').textContent = raw; }
  new bootstrap.Modal(document.getElementById('pbParamsModal')).show();
}
</script>
'''

CONVERSION_LOG_EMBED_HTML = '''
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
  body { background-color: #1a1a2e; color: #e0e0e0; font-size: 0.9rem; padding: 10px; }
  .table { background-color: #16213e; color: #e0e0e0; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.4); }
  .table thead { background-color: #0f3460; }
  .table th { color: #e2a03f; font-weight: bold; }
  .table td, .table th { border-color: #2a2a4a; padding: 0.4rem; }
  .btn { font-size: 0.8rem; padding: 3px 8px; }
  .btn-sm { font-size: 0.7rem; padding: 2px 6px; }
  .pagination .page-link { background-color: #16213e; border-color: #2a2a4a; color: #e0e0e0; }
  .pagination .page-item.active .page-link { background-color: #e2a03f; border-color: #e2a03f; color: #000; }
</style>
<h4>📋 Лог конверсий</h4>
<table class="table table-sm table-hover">
<thead>
  <tr>
    <th>ID</th><th>Время</th><th>Click ID</th><th>Выплата</th><th>Статус</th><th>Цель</th><th>Кампания</th><th>Оффер</th><th>Лендинг</th><th>IP</th><th>User-Agent</th><th>Страна</th><th>Город</th><th>Параметры</th>
  </tr>
</thead>
<tbody>
{% for r in rows %}
<tr>
  <td>{{ r[0] }}</td>
  <td>{{ r[1] }}</td>
  <td><code>{{ r[2] }}</code></td>
  <td>${{ "%.2f"|format(r[3]) }}</td>
  <td>{{ r[4] or '-' }}</td>   <!-- статус -->
  <td>{{ r[5] or '-' }}</td>   <!-- цель -->
  <td>{{ r[6] }}</td>           <!-- кампания -->
  <td>{{ r[7] }}</td>           <!-- оффер -->
  <td>{{ r[8] }}</td>           <!-- лендинг -->
  <td>{{ r[9] or '-' }}</td>    <!-- IP -->
  <td style="max-width:150px;overflow:hidden;text-overflow:ellipsis;">{{ r[10] or '-' }}</td> <!-- User-Agent -->
  <td>{{ r[11] or '-' }}</td>   <!-- страна -->
  <td>{{ r[12] or '-' }}</td>   <!-- город -->
  <td>
    {% if r[24] %}
      <button class="btn btn-sm btn-outline-info" onclick="showConvParams('{{ r[0] }}')">👁️</button>
      <pre id="conv-params-{{ r[0] }}" style="display:none;">{{ r[24] }}</pre>
    {% else %}—{% endif %}
  </td>
</tr>
{% endfor %}
</tbody>
</table>
<nav><ul class="pagination">{% for p in range(1,total_pages+1) %}<li class="page-item {{'active' if p==page}}"><a class="page-link" href="?page={{p}}&embed=1">{{p}}</a></li>{% endfor %}</ul></nav>

<div class="modal fade" id="convParamsModal" tabindex="-1">
  <div class="modal-dialog modal-lg"><div class="modal-content bg-dark text-light"><div class="modal-header"><h5>Параметры конверсии</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div><div class="modal-body"><pre id="convParamsContent" style="white-space:pre-wrap;word-break:break-all;"></pre></div></div></div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script>
function showConvParams(rowId) {
  const raw = document.getElementById('conv-params-' + rowId).textContent;
  try { const obj = JSON.parse(raw); document.getElementById('convParamsContent').textContent = JSON.stringify(obj, null, 2); }
  catch(e) { document.getElementById('convParamsContent').textContent = raw; }
  new bootstrap.Modal(document.getElementById('convParamsModal')).show();
}
</script>
'''

DASHBOARD_HTML = HEADER + '''
<h4>📊 Дашборд</h4>
<!-- Панель периода -->
<form class="row g-2 mb-3" method="get" id="periodForm">
  <div class="col-auto">
    <select class="form-select form-select-sm" name="period" onchange="handlePeriodChange(this.value)">
      <option value="all" selected>Всё время</option>
      <option value="today">Сегодня</option>
      <option value="yesterday">Вчера</option>
      <option value="3days">3 дня</option>
      <option value="week">Неделя</option>
      <option value="2weeks">2 недели</option>
      <option value="month">Месяц</option>
      <option value="year">Год</option>
      <option value="custom">Произвольный</option>
    </select>
  </div>
  <div class="col-auto" id="customDateFields" style="display:none;">
    <input type="date" class="form-control form-control-sm d-inline w-auto" name="start">
    <span class="text-light">—</span>
    <input type="date" class="form-control form-control-sm d-inline w-auto" name="end">
  </div>
  <div class="col-auto">
    <button type="submit" class="btn btn-sm btn-outline-warning">Применить</button>
  </div>
</form>

<!-- Сводка -->
<div class="row mb-4" id="summaryCards">
  <div class="col-md-2"><div class="card bg-dark text-light"><div class="card-body"><h6>Клики</h6><h4 id="sumClicks">—</h4></div></div></div>
  <div class="col-md-2"><div class="card bg-dark text-light"><div class="card-body"><h6>Лиды</h6><h4 id="sumLeads">—</h4></div></div></div>
  <div class="col-md-2"><div class="card bg-dark text-light"><div class="card-body"><h6>Аппрув</h6><h4 id="sumApproved">—</h4></div></div></div>
  <div class="col-md-2"><div class="card bg-dark text-light"><div class="card-body"><h6>Доход</h6><h4 id="sumRevenue">—</h4></div></div></div>
  <div class="col-md-2"><div class="card bg-dark text-light"><div class="card-body"><h6>Расход</h6><h4 id="sumCost">—</h4></div></div></div>
  <div class="col-md-2"><div class="card bg-dark text-light"><div class="card-body"><h6>Прибыль</h6><h4 id="sumProfit">—</h4></div></div></div>
</div>

<!-- График -->
<div class="card bg-dark mb-4">
  <div class="card-body">
    <canvas id="dashboardChart" height="100"></canvas>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
const ctx = document.getElementById('dashboardChart').getContext('2d');
let chart = null;

function handlePeriodChange(val) {
  document.getElementById('customDateFields').style.display = val === 'custom' ? 'block' : 'none';
  if (val !== 'custom') loadDashboardData();
}

document.getElementById('periodForm').addEventListener('submit', function(e) {
  e.preventDefault();
  loadDashboardData();
});

async function loadDashboardData() {
  const params = new FormData(document.getElementById('periodForm'));
  const query = new URLSearchParams(params).toString();
  const resp = await fetch('/dashboard/data?' + query);
  const data = await resp.json();

  // Сводка
  document.getElementById('sumClicks').textContent = data.summary.clicks;
  document.getElementById('sumLeads').textContent = data.summary.leads;
  document.getElementById('sumApproved').textContent = data.summary.approved;
  document.getElementById('sumRevenue').textContent = '$' + data.summary.revenue.toFixed(2);
  document.getElementById('sumCost').textContent = '$' + data.summary.cost.toFixed(4);
  document.getElementById('sumProfit').textContent = '$' + data.summary.profit.toFixed(2);

  // График
  if (chart) chart.destroy();
  chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.chart.labels,
      datasets: [
        {
          label: 'Доход',
          data: data.chart.revenue,
          borderColor: '#2ecc71',
          backgroundColor: 'rgba(46,204,113,0.1)',
          tension: 0.2
        },
        {
          label: 'Расход',
          data: data.chart.cost,
          borderColor: '#e74c3c',
          backgroundColor: 'rgba(231,76,60,0.1)',
          tension: 0.2
        }
      ]
    },
    options: {
      responsive: true,
      scales: {
        y: { beginAtZero: true, ticks: { color: '#e0e0e0' } },
        x: { ticks: { color: '#e0e0e0' } }
      },
      plugins: { legend: { labels: { color: '#e0e0e0' } } }
    }
  });
}

// Загрузка при открытии
document.addEventListener('DOMContentLoaded', loadDashboardData);
</script>
''' + FOOTER

if __name__ == '__main__':
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print("="*50)
    print("Мародёр Трекер запущен!")
    print(f"Локально: http://{local_ip}:5000")
    if DOMAIN != 'localhost':
        print(f"Домен:    http://{DOMAIN}")
    else:
        print("Домен не настроен. Перейди в /settings для указания домена.")
    print("="*50)
    app.run(host='0.0.0.0', port=5000)