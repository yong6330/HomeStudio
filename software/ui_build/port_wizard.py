"""Usage: python port_wizard.py <stitch export dir> software/frontend/views
Wizard + family invite screens (Stitch export 2, screens _4 _1 _3 _5 _2) -> views/{start,join,discover,camconn,family}.html"""
import re, sys
SRC = sys.argv[1]; OUT = sys.argv[2]
AVATAR = '<div class="w-8 h-8 rounded-full bg-primary flex items-center justify-center"><span class="material-symbols-outlined text-on-primary text-[18px]">person</span></div>'
AVATAR_LINK = '<a href="#status" aria-label="계정" class="w-8 h-8 rounded-full bg-primary flex items-center justify-center"><span class="material-symbols-outlined text-on-primary text-[18px]">person</span></a>'
ERR = ('<div class="hidden flex items-start gap-1.5 mt-1 px-1 py-1.5 rounded-lg bg-error-container/30" id="{id}">'
       '<span class="material-symbols-outlined text-[17px] text-error shrink-0 mt-0.5" style="font-variation-settings: \'FILL\' 1;">error</span>'
       '<p class="font-body-sm text-body-sm text-on-error-container leading-tight" data-k="{id}"></p></div>')

class View:
    def __init__(self, d, name):
        s = open(f"{SRC}/{d}/code.html").read()
        body = re.search(r'<body class="([^"]*)">(.*)</body>', s, re.S)
        s = f'<!--body class="{body.group(1)}"-->\n' + body.group(2)
        s = re.sub(r"<script.*?</script>", "", s, flags=re.S)
        s = re.sub(r' data-alt="[^"]*"', '', s)
        s = re.sub(r'(<img alt="Minimal and cute hamster[^"]*" class="[^"]*" src=")https://lh3[^"]+', r'\1assets/mascot.png', s)
        s = s.replace("홈 스튜디오", "HomeStudio").replace("홈스튜디오", "HomeStudio")
        self.s, self.name = s, name
    def r(self, old, new, n=1):
        c = self.s.count(old); assert c == n, f"{self.name}: expected {n} got {c}: {old[:100]!r}"
        self.s = self.s.replace(old, new); return self
    def rx(self, pat, new, n=1):
        self.s, c = re.subn(pat, new, self.s, flags=re.S); assert c == n, f"{self.name}: {pat[:80]} {c}"; return self
    def save(self):
        assert "lh3.googleusercontent" not in self.s and "https://" not in self.s and "onclick=\"select" not in self.s, self.name
        open(f"{OUT}/{self.name}.html", "w").write(self.s)

# ---------- _4 start choice (public, before signup)
v = View("_4", "start")
v.r(AVATAR, AVATAR_LINK.replace('href="#status"', 'href="#welcome"'))
v.rx(r'(<img alt="HomeStudio 마스코트" class="[^"]*" src=")https://lh3[^"]+', r'\1assets/mascot.png')
v.r(' onclick="selectOption(\'create\')"', ' data-pick="create"')
v.r(' onclick="selectOption(\'join\')"', ' data-pick="join"')
v.r('<span>야간 감지 센서 및 실시간 쳇바퀴 분석 연동</span>', '<span>카메라 화면으로 활동량·쳇바퀴 분석</span>')  # no extra sensors exist
v.r('''<div class="mt-space-xl flex flex-col gap-3">''', '''<div class="mt-space-xl flex flex-col gap-3">
''' + ERR.format(id="start-error"))
v.save()

# ---------- _1 join family home (invite code + preview)
v = View("_1", "join")
v.r(AVATAR, AVATAR_LINK.replace('href="#status"', 'href="#welcome"'))
v.r('<span class="font-label-sm text-label-sm text-primary">초대 링크 확인됨</span>', '<span class="font-label-sm text-label-sm text-primary" data-k="chip">초대 코드 입력</span>')
v.r('''<span class="inline-flex items-center gap-1 font-label-sm text-label-sm text-primary">''', '''<span class="hidden inline-flex items-center gap-1 font-label-sm text-label-sm text-primary" id="code-ok">''')
v.rx(r'<div class="grid grid-cols-8 gap-1.5 w-full select-none" id="code-slots">.*?</div>\n</div>\n<!-- Quick Paste',
     '<div class="grid grid-cols-8 gap-1.5 w-full select-none cursor-text" id="code-slots"></div>\n'
     '<input class="sr-only" id="invite-code-input" autocomplete="off" autocapitalize="characters" spellcheck="false" maxlength="9" inputmode="text"/>\n'
     '<!-- Quick Paste')
v.r('<span class="font-label-sm text-label-sm text-on-surface-variant">클립보드 감지: 8K2M9P4B</span>', '<span class="font-label-sm text-label-sm text-on-surface-variant" data-k="code_hint">코드 칸을 눌러 입력하세요</span>')
v.r('''<button class="h-9 px-3 rounded-full bg-surface-container-high text-on-surface hover:bg-surface-bright active:scale-95 transition-all flex items-center gap-1.5" type="button">''',
    '''<button class="h-9 px-3 rounded-full bg-surface-container-high text-on-surface hover:bg-surface-bright active:scale-95 transition-all flex items-center gap-1.5" id="btn-paste" type="button">''')
v.r('<span class="font-label-md text-label-md text-primary">붙여넣기 완료</span>', '<span class="font-label-md text-label-md text-primary" data-k="paste_label">붙여넣기</span>')
v.r('</section>\n<!-- Verified Home Preview Card -->\n<section class="mb-6">', ERR.format(id="join-error") + '\n</section>\n<!-- Verified Home Preview Card -->\n<section class="hidden mb-6" id="preview">')
v.rx(r'(<img alt="반려 햄스터 보리 프로필" class="[^"]*" src=")https://lh3[^"]+', r'\1assets/mascot.png')
v.r('<h3 class="font-headline-sm text-headline-sm text-on-surface truncate">보리의 아늑한 별장</h3>', '<h3 class="font-headline-sm text-headline-sm text-on-surface truncate" data-k="home_name">보리의 아늑한 별장</h3>')
v.r('<p class="font-body-sm text-body-sm text-secondary truncate">골든 햄스터 · 보리 (125g, 6개월)</p>', '<p class="font-body-sm text-body-sm text-secondary truncate" data-k="pet_line">골든 햄스터 · 보리 (125g, 6개월)</p>')
v.r('<span class="font-body-sm text-body-sm text-on-surface font-medium">엄마집사 (bory_mom@...)</span>', '<span class="font-body-sm text-body-sm text-on-surface font-medium" data-k="admin">엄마집사 (bory_mom@...)</span>')
v.r('<span class="font-body-sm text-body-sm text-on-surface font-medium">HomeStudio 캠 Pro 1대</span>', '<span class="font-body-sm text-body-sm text-on-surface font-medium" data-k="device">HomeStudio 캠 Pro 1대</span>')
v.r('<span class="font-body-sm text-body-sm text-on-surface font-medium">실시간 스트리밍 &amp; 타임라인 열람</span>', '<span class="font-body-sm text-body-sm text-on-surface font-medium">실시간 스냅샷 &amp; 타임라인 열람</span>')
v.r('''          참여 즉시 보리의 수면 및 쳇바퀴 활동 알림을 함께 수신할 수 있습니다.''', '''          <span data-k="note">참여 즉시 보리의 수면 및 쳇바퀴 활동 알림을 함께 수신할 수 있습니다.</span>''')
v.r('''<button class="w-full h-14 rounded-xl bg-primary text-on-primary font-label-lg text-label-lg flex items-center justify-center gap-2 shadow-lg hover:opacity-95 active:scale-[0.99] transition-all" type="button">''',
    '''<button class="w-full h-14 rounded-xl bg-primary text-on-primary font-label-lg text-label-lg flex items-center justify-center gap-2 shadow-lg hover:opacity-95 active:scale-[0.99] transition-all disabled:opacity-40" id="btn-join" disabled type="button">''')
v.r('''<button class="mt-1 font-label-md text-label-md text-primary hover:underline underline-offset-4 flex items-center gap-1" type="button">''',
    '''<button class="mt-1 font-label-md text-label-md text-primary hover:underline underline-offset-4 flex items-center gap-1" id="btn-nocode" type="button">''')
v.save()

# ---------- _3 camera discovery
v = View("_3", "discover")
v.r(AVATAR, AVATAR_LINK)
v.r('<span>새로운 홈 생성 (2/3단계)</span>', '<span data-k="step">새로운 홈 생성 (2/3단계)</span>')
v.r('<span>로컬 탐색 활성화됨</span>', '<span data-k="scope">로컬 탐색 활성화됨</span>')
v.r('<h2 class="font-headline-md text-headline-md text-on-surface">네트워크에서 카메라를 찾고 있어요</h2>', '<h2 class="font-headline-md text-headline-md text-on-surface" data-k="title">네트워크에서 카메라를 찾고 있어요</h2>')
v.r('''      동일한 Wi-Fi 네트워크에 연결된 HomeStudio 캠을 자동으로 감지합니다.''', '''      HomeStudio PC와 같은 네트워크(유선·Wi-Fi)에 연결된 카메라를 자동으로 감지합니다.''')
v.r('<div class="relative w-44 h-44 flex items-center justify-center my-2">', '<div class="relative w-44 h-44 flex items-center justify-center my-2" id="radar">')
v.r('<span class="font-label-md text-label-md font-medium text-primary">Wi-Fi (5GHz / 2.4GHz) 스캔 중...</span>', '<span class="font-label-md text-label-md font-medium text-primary" data-k="scan">유선 · Wi-Fi 스캔 중...</span>')
v.r('<span class="text-on-surface-variant font-label-md text-label-md">· 2대 발견</span>', '<span class="text-on-surface-variant font-label-md text-label-md" data-k="found">· 0대 발견</span>')
v.r('<span class="font-label-sm text-label-sm text-on-surface-variant">신호 강도 순 정렬</span>', '<span class="font-label-sm text-label-sm text-on-surface-variant">연결 가능 순 정렬</span>')
# card templates: selectable (card 1) and already-registered (card 2)
c1 = v.s.index('<!-- Card 1: Selected & Recommended -->'); c2 = v.s.index('<!-- Card 2: Already Registered to Another Home -->'); c3 = v.s.index('<!-- Collapsible Troubleshooting')
card = v.s[c1:c2]
card = card.replace(' id="deviceCard1" onclick="selectDevice(1)"', ' data-tpl="cam"').replace(' id="radioIndicator1"', ' data-radio')
card = card.replace('<span class="material-symbols-outlined text-[26px]" style="font-variation-settings: \'FILL\' 1;">nest_cam_iq_outdoor</span>', '<span class="material-symbols-outlined text-[26px]" style="font-variation-settings: \'FILL\' 1;">nest_cam_iq_outdoor</span>')
card = card.replace('<span class="font-label-lg text-label-lg text-on-surface">HomeStudio 캠 Pro</span>', '<span class="font-label-lg text-label-lg text-on-surface" data-k="model">HomeStudio 캠 Pro</span>')
card = card.replace('<span class="px-1.5 py-0.5 rounded bg-primary/20 text-primary font-label-sm text-label-sm">신규 감지</span>', '<span class="px-1.5 py-0.5 rounded bg-primary/20 text-primary font-label-sm text-label-sm" data-k="tag">신규 감지</span>')
card = card.replace('<p class="font-body-sm text-body-sm text-on-surface-variant mt-0.5">IP 192.168.1.142 · MAC A4:C3:F0:8E:21</p>', '<p class="font-body-sm text-body-sm text-on-surface-variant mt-0.5" data-k="addr">IP 192.168.1.142 · MAC A4:C3:F0:8E:21</p>')
card = card.replace('<span class="material-symbols-outlined text-[18px] text-primary">network_wifi</span>\n<span>Wi-Fi (신호 매우 우수 ▮▮▮▮)</span>', '<span class="material-symbols-outlined text-[18px] text-primary" data-k="net_icon">network_wifi</span>\n<span data-k="net">Wi-Fi (신호 매우 우수 ▮▮▮▮)</span>')
assert card.count("data-k") == 5, card
reg = v.s[c2:c3].replace(' id="deviceCard2" onclick="selectDevice(2)"', ' data-tpl="camreg"').replace(' id="radioIndicator2"', ' data-radio')
reg = reg.replace('cursor-not-allowed opacity-75 ', 'cursor-pointer opacity-75 ')
reg = reg.replace('<span class="font-label-lg text-label-lg text-secondary">HomeStudio 캠 Lite (거실)</span>', '<span class="font-label-lg text-label-lg text-secondary" data-k="model">HomeStudio 캠 Lite (거실)</span>')
reg = reg.replace('<p class="font-body-sm text-body-sm text-secondary font-label-sm mt-0.5">IP 192.168.1.155 · LAN 포트 직결</p>', '<p class="font-body-sm text-body-sm text-secondary font-label-sm mt-0.5" data-k="addr">IP 192.168.1.155 · LAN 포트 직결</p>')
reg = reg.replace('<span class="material-symbols-outlined text-[18px]">lan</span>\n<span>유선 LAN 연결됨</span>', '<span class="material-symbols-outlined text-[18px]" data-k="net_icon">lan</span>\n<span data-k="net">유선 LAN 연결됨</span>')
reg = reg.replace('<span>이미 다른 홈에 등록됨</span>', '<span>이미 이 홈에 등록됨</span>')
assert reg.count("data-k") == 4, reg
v.s = v.s[:c1] + card + reg + v.s[c3:]
v.r('<div class="space-y-3">\n<div class="flex items-center justify-between px-1">', '<div class="space-y-3" id="cam-list">\n<div class="flex items-center justify-between px-1">')
v.r(' onclick="toggleHelpSection()"', ' id="btn-help"')
v.r(' onclick="restartScan()"', ' id="btn-rescan"')
v.r('''          1) 스마트폰이 카메라와 <strong>동일한 Wi-Fi(2.4/5GHz)</strong>에 접속되어 있는지 확인해 주세요.<br/>
          2) 카메라 전면 LED가 <strong>초록색으로 깜빡</strong>거리는지 확인해 주세요.''',
    '''          1) 카메라가 HomeStudio PC와 <strong>같은 공유기(유선 또는 Wi-Fi)</strong>에 연결되어 있는지 확인해 주세요.<br/>
          2) 카메라 <strong>전원</strong>이 켜져 있고 부팅이 끝났는지(약 1분) 확인해 주세요.''')
v.r('<div class="p-3.5 rounded-xl bg-tertiary/10 space-y-1.5">', '<div class="p-3.5 rounded-xl bg-tertiary/10 space-y-1.5" id="auth-tip">')
v.r('<span>카메라 계정 확인 및 초기화 안내</span>', '<span data-k="auth_title">카메라 계정 확인 및 초기화 안내</span>')
v.r('''          이전에 등록된 적 있는 카메라는 보안상 자동으로 연결되지 않습니다. 기기 하단의 <strong>RESET 버튼을 5초간</strong> 눌러 딩동 소리가 날 때까지 초기화한 후 다시 시도해 주세요.''',
    '''          <span data-html="auth_text">카메라 관리자 페이지에 HomeStudio 전용 계정이 있어야 연결할 수 있어요. 계정 비밀번호가 맞지 않으면 카메라 잠금을 막기 위해 잠시 후 다시 시도해요.</span>''')
v.r(' onclick="handleConnectCamera()"', ' disabled')
v.r('id="confirmConnectionBtn"', 'id="confirmConnectionBtn" class-x', 1)
v.s = v.s.replace(' class-x', '')
v.r('<span>이 카메라 연결하기</span>', '<span data-k="cta">이 카메라 연결하기</span>')
v.r('bg-primary text-on-primary font-label-lg text-label-lg font-bold flex items-center justify-center gap-2 shadow-lg hover:brightness-105 active:scale-[0.99] transition-all" id="confirmConnectionBtn"',
    'bg-primary text-on-primary font-label-lg text-label-lg font-bold flex items-center justify-center gap-2 shadow-lg hover:brightness-105 active:scale-[0.99] transition-all disabled:opacity-50" id="confirmConnectionBtn"')
v.r('''<p class="text-center font-label-sm text-label-sm text-on-surface-variant mt-2.5">''', ERR.format(id="discover-error") + '''\n<p class="text-center font-label-sm text-label-sm text-on-surface-variant mt-2.5">''')
v.save()

# ---------- _5 camera connected
v = View("_5", "camconn")
v.r(AVATAR, AVATAR_LINK)
v.r('<span class="font-label-md text-label-md text-secondary">케이지 셋업 4단계</span>', '<span class="font-label-md text-label-md text-secondary">케이지 셋업 3단계</span>')
v.r('font-label-sm text-label-sm">4</span>', 'font-label-sm text-label-sm">3</span>')
v.r('<span class="font-label-sm text-label-sm font-semibold tracking-wide">실시간 연결 성공</span>', '<span class="font-label-sm text-label-sm font-semibold tracking-wide" data-k="badge">실시간 연결 성공</span>')
v.rx(r'<img class="w-full h-full object-cover opacity-85 group-hover:scale-105 transition-transform duration-700 ease-out" src="https://lh3[^"]+"/>',
     '<img alt="케이지 최신 스냅샷" class="w-full h-full object-cover opacity-85 group-hover:scale-105 transition-transform duration-700 ease-out" id="cam-img" src=""/>')
v.r('''<span class="w-1.5 h-1.5 rounded-full bg-primary animate-ping"></span>
          LIVE 1080p 30fps''', '''<span class="w-1.5 h-1.5 rounded-full bg-primary animate-ping"></span>
          <span data-k="live">LIVE 1080p 30fps</span>''')
v.r('''<span class="material-symbols-outlined text-[13px] text-tertiary">nightlight</span>
          IR ON''', '''<span class="material-symbols-outlined text-[13px] text-tertiary" data-k="dp_icon">nightlight</span>
          <span data-k="daypart">IR ON</span>''')
v.r('''<span class="material-symbols-outlined text-[14px] text-primary">wifi</span>
        -42 dBm''', '''<span class="material-symbols-outlined text-[14px] text-primary" data-k="net_icon">wifi</span>
        <span data-k="net_short">-42 dBm</span>''')
v.r('<span class="font-label-sm text-label-sm text-on-surface">정상 스트리밍 중</span>', '<span class="font-label-sm text-label-sm text-on-surface" data-k="cam_label">정상 스트리밍 중</span>')
v.r('type="text" value="보리네 케이지 1층"/>', 'type="text" maxlength="20" value=""/>')
v.r('<span class="font-label-sm text-label-sm truncate">연결 방식</span>\n</div>\n<span class="font-label-md text-label-md text-on-surface font-medium truncate">5GHz 초고속</span>',
    '<span class="font-label-sm text-label-sm truncate">연결 방식</span>\n</div>\n<span class="font-label-md text-label-md text-on-surface font-medium truncate" data-k="net">5GHz 초고속</span>')
v.r('<span class="material-symbols-outlined text-[14px] text-primary">signal_cellular_alt</span>\n<span class="font-label-sm text-label-sm truncate">신호 강도</span>\n</div>\n<span class="font-label-md text-label-md text-on-surface font-medium truncate">우수 (99.8%)</span>',
    '<span class="material-symbols-outlined text-[14px] text-primary">lan</span>\n<span class="font-label-sm text-label-sm truncate">IP 주소</span>\n</div>\n<span class="font-label-md text-label-md text-on-surface font-medium truncate" data-k="ip">우수 (99.8%)</span>')
v.r('<span class="font-label-md text-label-md text-on-surface font-medium truncate">v2.4.1 최신</span>', '<span class="font-label-md text-label-md text-on-surface font-medium truncate" data-k="fw">v2.4.1 최신</span>')
v.r('        케이지 AI 감지존 예고', '        케이지 감지 영역 예고')
v.r('        다음 단계에서 쳇바퀴, 급수기, 은신처의 AI 감지 영역(케이지 존)을 지정하게 됩니다.', '        다음 단계에서 케이지, 쳇바퀴, 먹이 그릇, 은신처의 감지 영역을 지정하게 됩니다.')
v.r('      모든 연결 정보는 기기 내에 암호화되어 안전하게 보관됩니다.', '      카메라 계정 정보는 HomeStudio PC 안에 암호화되어 보관됩니다.')
v.r('''<div class="w-full flex flex-col gap-space-xs mt-auto">''', '''<div class="w-full flex flex-col gap-space-xs mt-auto">\n''' + ERR.format(id="camconn-error"))
v.save()

# ---------- _2 family invite (admin, from 상태 > 가족 초대)
v = View("_2", "family")
v.r(AVATAR, AVATAR_LINK)
v.r('''        초대 링크나 코드를 공유하여 가족과 함께 보리의 조용한 밤과 소중한 일상을 실시간으로 돌보세요.''', '''        <span data-k="hero">초대 링크나 코드를 공유하여 가족과 함께 보리의 조용한 밤과 소중한 일상을 실시간으로 돌보세요.</span>''')
v.r('<section class="rounded-xl bg-surface-container-low p-space-lg shadow-xl relative overflow-hidden flex flex-col space-y-space-lg">', '<section class="rounded-xl bg-surface-container-low p-space-lg shadow-xl relative overflow-hidden flex flex-col space-y-space-lg" id="invite-card">')
v.r('<span class="font-label-sm text-label-sm font-semibold">유효한 초대 링크</span>', '<span class="font-label-sm text-label-sm font-semibold" data-k="link_chip">유효한 초대 링크</span>')
v.r('''          https://homestudio.kr/join?code=BORY2025''', '''<span data-k="url">-</span>''')
v.r('<span class="font-label-sm text-label-sm text-on-surface-variant tracking-wider uppercase">보리 전용 케어 접속 코드</span>', '<span class="font-label-sm text-label-sm text-on-surface-variant tracking-wider uppercase" data-k="code_label">보리 전용 케어 접속 코드</span>')
v.r('''        BORY-2025''', '''<span data-k="code">----</span>''')
v.r('        HomeStudio 앱 설치 후 위 코드를 직접 입력해도 연결됩니다.', '        HomeStudio 시작 화면의 \'가족 코드로 시작하기\'에 위 코드를 직접 입력해도 연결됩니다.')
v.r('<span class="material-symbols-outlined text-[20px]">link</span>\n<span>링크 복사</span>', '<span class="material-symbols-outlined text-[20px]">link</span>\n<span data-k="main_btn">링크 복사</span>')
v.r('<span class="font-label-md text-label-md font-medium text-on-surface">24시간 후 만료 (오늘 23:59까지 유효)</span>', '<span class="font-label-md text-label-md font-medium text-on-surface" data-k="expiry">24시간 후 만료 (오늘 23:59까지 유효)</span>')
v.r('        보리의 사생활 보호를 위해 1회 참여 완료 시 발급된 코드는 자동으로 안전하게 비활성화됩니다.', '        <span data-k="expiry_note">보리의 사생활 보호를 위해 1회 참여 완료 시 발급된 코드는 자동으로 안전하게 비활성화됩니다.</span>')
v.r('<span class="font-label-sm text-label-sm px-space-sm py-0.5 rounded-full bg-surface-container-high text-primary">1건</span>', '<span class="font-label-sm text-label-sm px-space-sm py-0.5 rounded-full bg-surface-container-high text-primary" data-k="pending_count">1건</span>')
v.r('<div class="rounded-xl bg-surface-container-low p-space-md flex items-center justify-between">', '<div class="rounded-xl bg-surface-container-low p-space-md flex items-center justify-between" data-tpl="pending">')
v.r('<span class="font-label-lg text-label-lg text-on-surface truncate">가족 집사 1</span>', '<span class="font-label-lg text-label-lg text-on-surface truncate" data-k="name">가족 집사 1</span>')
v.r('<span class="font-body-sm text-body-sm text-secondary truncate">10분 전 전송됨 · 유효시간 23시간 50분 남음</span>', '<span class="font-body-sm text-body-sm text-secondary truncate" data-k="sub">10분 전 전송됨 · 유효시간 23시간 50분 남음</span>')
v.r(''' onclick="confirm('가족 집사 1님의 초대를 취소하시겠습니까?')" type="button">''', ''' data-revoke type="button">''')
v.r('<h3 class="font-headline-sm text-headline-sm text-on-surface">대기 중인 초대</h3>', '<h3 class="font-headline-sm text-headline-sm text-on-surface">대기 중인 초대</h3>')
v.r('<section class="flex flex-col space-y-space-sm">\n<div class="flex items-center justify-between px-space-xs">\n<h3 class="font-headline-sm text-headline-sm text-on-surface">대기 중인 초대</h3>',
    '<section class="flex flex-col space-y-space-sm" id="pending-sec">\n<div class="flex items-center justify-between px-space-xs">\n<h3 class="font-headline-sm text-headline-sm text-on-surface">대기 중인 초대</h3>')
v.r('<span class="font-label-sm text-label-sm text-secondary">2명 활동 중</span>', '<span class="font-label-sm text-label-sm text-secondary" data-k="member_count">2명 활동 중</span>')
m1 = v.s.index('<!-- Member 1: Admin / Self -->'); m2 = v.s.index('<!-- Member 2: Co-guardian -->'); m3 = v.s.index('</div>\n</section>\n<!-- Security', m2)
adm = v.s[m1:m2].replace('<div class="p-space-md flex items-center justify-between">', '<div class="p-space-md flex items-center justify-between" data-tpl="admin">', 1)
adm = adm.replace('<span class="font-label-lg text-label-lg text-on-surface">엄마집사</span>', '<span class="font-label-lg text-label-lg text-on-surface" data-k="name">엄마집사</span>')
adm = adm.replace('<span class="font-label-sm text-label-sm text-primary px-1.5 py-0.5 rounded bg-primary/10">나</span>', '<span class="font-label-sm text-label-sm text-primary px-1.5 py-0.5 rounded bg-primary/10" data-show="me">나</span>')
mem = v.s[m2:m3].replace('<div class="p-space-md flex items-center justify-between">', '<div class="p-space-md flex items-center justify-between" data-tpl="member">', 1)
mem = mem.replace('<span class="font-label-lg text-label-lg text-on-surface">아빠집사</span>', '<span class="font-label-lg text-label-lg text-on-surface" data-k="name">아빠집사</span>')
mem = mem.replace('<span class="font-label-sm text-label-sm text-secondary px-1.5 py-0.5 rounded bg-surface-variant">공동 집사</span>', '<span class="font-label-sm text-label-sm text-secondary px-1.5 py-0.5 rounded bg-surface-variant" data-k="role">공동 집사</span><span class="font-label-sm text-label-sm text-primary px-1.5 py-0.5 rounded bg-primary/10" data-show="me">나</span>')
mem = mem.replace('<span class="font-body-sm text-body-sm text-secondary">실시간 스트리밍 &amp; 모니터링 허용</span>', '<span class="font-body-sm text-body-sm text-secondary" data-k="sub">실시간 스냅샷 &amp; 모니터링 허용</span>')
mem = mem.replace('<span>라이브 시청 가능</span>', '<span data-k="right">라이브 시청 가능</span>')
v.s = v.s[:m1] + adm + mem + v.s[m3:]
v.r('<span class="font-label-md text-label-md text-on-surface font-semibold">보안 스트리밍 보호 중</span>', '<span class="font-label-md text-label-md text-on-surface font-semibold">보안 연결 보호 중</span>')
v.r('        HomeStudio는 종단간 암호화(E2EE)로 등록된 가족 구성원에게만 안전하게 영상을 스트리밍하며, 외부 유출을 원천 차단합니다.',
    '        HomeStudio 영상은 집 PC에만 저장되고, 로그인한 가족에게만 Tailscale 암호화 연결로 보여 줘요. 외부 클라우드로 보내지 않아요.')
v.save()
print("ok")
