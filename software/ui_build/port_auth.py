from port_common import *

# ---- welcome (as-is; buttons wired by id in app.js)
View("welcome").save()

# ---- login
v = View("login")
v.r(AVATAR, AVATAR_LINK.replace('href="#status"', 'href="#welcome"'))
v.r('<form class="flex flex-col gap-4" onsubmit="event.preventDefault();">', '<form class="flex flex-col gap-4" id="login-form" novalidate>')
v.r('''<span class="font-label-sm text-label-sm text-primary flex items-center gap-0.5">''', '''<span class="hidden font-label-sm text-label-sm text-primary flex items-center gap-0.5" id="email-ok">''')
v.r('type="email" value="bory_mom@homestudio.kr"/>', 'type="email" autocomplete="username" required/>')
v.r('''<div class="absolute right-3.5 flex items-center justify-center pointer-events-none text-primary">''', '''<div class="hidden absolute right-3.5 flex items-center justify-center pointer-events-none text-primary" id="email-ok-icon">''')
# password field: neutral by default, error state toggled by app.js (Stitch error classes kept in JS)
v.r('<label class="font-label-md text-label-md text-error" for="password">비밀번호</label>', '<label class="font-label-md text-label-md text-on-surface-variant" for="password" id="pw-label">비밀번호</label>')
v.r('<span class="font-label-sm text-label-sm text-error/90">입력 오류 (1/5회)</span>', '<span class="hidden font-label-sm text-label-sm text-error/90" id="pw-count"></span>')
v.r('<div class="absolute left-3.5 flex items-center justify-center pointer-events-none text-error">', '<div class="absolute left-3.5 flex items-center justify-center pointer-events-none text-on-surface-variant" id="pw-lock">')
v.r('class="w-full h-13 py-3.5 pl-11 pr-12 rounded-xl bg-error-container/40 text-on-surface font-body-md text-body-md shadow-[0_0_16px_rgba(147,0,10,0.25)] focus:outline-none transition-all tracking-wider" id="password" placeholder="비밀번호" type="password" value="password123!"/>',
    'class="w-full h-13 py-3.5 pl-11 pr-12 rounded-xl bg-surface-container text-on-surface font-body-md text-body-md focus:outline-none focus:bg-surface-container-high transition-all tracking-wider" id="password" placeholder="비밀번호" type="password" autocomplete="current-password" required/>')
v.r('<div class="flex items-start gap-1.5 mt-1 px-1 py-1.5 rounded-lg bg-error-container/30">', '<div class="hidden flex items-start gap-1.5 mt-1 px-1 py-1.5 rounded-lg bg-error-container/30" id="login-error">')
v.r('''          이메일 또는 비밀번호가 일치하지 않습니다. <span class="text-error font-medium">(5회 실패 시 15분 잠금)</span>''',
    '''          <span data-k="login_error">이메일 또는 비밀번호가 일치하지 않습니다.</span> <span class="text-error font-medium">(5회 실패 시 15분 잠금)</span>''')
v.r('<input checked="" class="peer sr-only" id="rememberMe" type="checkbox"/>', '<input class="peer sr-only" id="rememberMe" type="checkbox"/>')
v.r('''<button class="font-label-md text-label-md text-on-surface-variant hover:text-primary transition-colors py-1" type="button">''', '''<button class="font-label-md text-label-md text-on-surface-variant hover:text-primary transition-colors py-1" id="btn-forgot" type="button">''')
v.r('''<button class="w-full p-4 rounded-2xl bg-surface-container hover:bg-surface-container-high active:scale-[0.99] transition-all flex items-center justify-between text-left group" type="button">''', '''<button class="w-full p-4 rounded-2xl bg-surface-container hover:bg-surface-container-high active:scale-[0.99] transition-all flex items-center justify-between text-left group" id="btn-pin" type="button">''')
v.r('<span class="font-label-sm text-label-sm text-on-surface font-semibold truncate">새벽 02:40 현재 HomeStudio 상태</span>', '<span class="font-label-sm text-label-sm text-on-surface font-semibold truncate"><span data-k="now">--:--</span> 현재 HomeStudio 상태</span>')
v.r('<span class="font-body-sm text-body-sm text-on-surface-variant truncate">보리가 쳇바퀴에서 활발히 산책 중이에요</span>', '<span class="font-body-sm text-body-sm text-on-surface-variant truncate">로그인하면 오늘의 활동 기록을 볼 수 있어요</span>')
v.r('''<button class="font-label-lg text-label-lg text-primary hover:underline transition-all ml-1" type="button">''', '''<button class="font-label-lg text-label-lg text-primary hover:underline transition-all ml-1" id="btn-signup" type="button">''')
v.save()

# ---- forgot / reset (no Stitch screen: composed from the login screen's own components)
f = View("login")
f.r(AVATAR, AVATAR_LINK.replace('href="#status"', 'href="#welcome"'))
f.r('Email Login</h1>', 'Password Reset</h1>')
f.r('<span class="font-label-sm text-label-sm text-on-surface-variant">야간 안심 모니터링 케어</span>', '<span class="font-label-sm text-label-sm text-on-surface-variant">계정 복구</span>')
f.r('''HomeStudio 계정으로
로그인해주세요</h2>''', '''비밀번호를
다시 설정해주세요</h2>''')
f.r('등록된 이메일 주소와 비밀번호를 입력해주세요.</p>', '가입한 이메일로 6자리 재설정 코드를 보내드려요.</p>')
f.r('<form class="flex flex-col gap-4" onsubmit="event.preventDefault();">', '<form class="flex flex-col gap-4" id="reset-form" novalidate>')
f.r('''<span class="font-label-sm text-label-sm text-primary flex items-center gap-0.5">''', '''<span class="hidden font-label-sm text-label-sm text-primary flex items-center gap-0.5" id="email-ok">''')
f.r('''          확인됨''', '''          코드 발송됨''')
f.r('type="email" value="bory_mom@homestudio.kr"/>', 'type="email" autocomplete="username" required/>')
f.r('''<div class="absolute right-3.5 flex items-center justify-center pointer-events-none text-primary">''', '''<div class="hidden absolute right-3.5 flex items-center justify-center pointer-events-none text-primary" id="email-ok-icon">''')
# password block -> code + new password + confirm (same field component)
start = f.s.index('<!-- Password Field (Active Error State) -->')
end = f.s.index('<!-- Options Row: Remember Me & Forgot Password -->')
field = lambda fid, label, icon, ph, typ, extra="": f'''<div class="flex flex-col gap-1.5 reset-step2 hidden">
<label class="font-label-md text-label-md text-on-surface-variant" for="{fid}">{label}</label>
<div class="relative flex items-center">
<div class="absolute left-3.5 flex items-center justify-center pointer-events-none text-on-surface-variant">
<span class="material-symbols-outlined text-[20px]">{icon}</span>
</div>
<input class="w-full h-13 py-3.5 pl-11 pr-11 rounded-xl bg-surface-container text-on-surface font-body-md text-body-md focus:outline-none focus:bg-surface-container-high transition-colors" id="{fid}" placeholder="{ph}" type="{typ}" {extra}/>
</div>
</div>
'''
rules = open(RAW + "signup.html").read()
grid = rules[rules.index('<div class="grid grid-cols-2 gap-x-2'):rules.index('<!-- Password Confirm Input Field -->')]
grid = grid[:grid.rindex('</div>')]  # drop the closing tag of the password field wrapper
f.s = (f.s[:start] + field("reset-code", "재설정 코드 (6자리)", "pin", "000000", "text", 'inputmode="numeric" maxlength="6" autocomplete="one-time-code"')
       + field("reset-password", "새 비밀번호", "lock", "새 비밀번호", "password", 'autocomplete="new-password"')
       + '<div class="reset-step2 hidden">' + grid + '</div>\n'
       + field("reset-confirm", "새 비밀번호 확인", "lock_reset", "비밀번호 재입력", "password", 'autocomplete="new-password"')
       + ERR.format(id="reset-error") + '\n' + f.s[end:])
f.rx(r'<!-- Options Row: Remember Me & Forgot Password -->.*?(?=<!-- Primary Login Button -->)', '')
f.r('<span>로그인</span>', '<span id="reset-cta">재설정 코드 받기</span>')
f.rx(r'<!-- Divider Section -->.*?<!-- Bottom Navigation / Signup Helper -->', '<!-- Bottom Navigation / Signup Helper -->')
f.r('<span class="font-body-md text-body-md text-on-surface-variant">계정이 없으신가요?</span>', '<span class="font-body-md text-body-md text-on-surface-variant">비밀번호가 기억나셨나요?</span>')
f.r('''<button class="font-label-lg text-label-lg text-primary hover:underline transition-all ml-1" type="button">
      회원가입하기''', '''<button class="font-label-lg text-label-lg text-primary hover:underline transition-all ml-1" id="btn-login" type="button">
      로그인하기''')
f.s = f.s.replace('''<span class="material-symbols-outlined text-[15px]" style="font-variation-settings: 'FILL' 1;">check_circle</span>''', '''<span class="material-symbols-outlined text-[15px]" style="font-variation-settings: 'FILL' 1;">radio_button_unchecked</span>''')
f.save("forgot")

# ---- signup (admin first run, or family invite)
v = View("signup")
v.r(AVATAR, AVATAR_LINK.replace('href="#status"', 'href="#welcome"'))
v.r('''        1/5 단계''', '''        <span data-k="step">1/5 단계</span>''')
v.r('<div class="h-full bg-primary-container rounded-full w-1/5 transition-all duration-500 ease-out"></div>', '<div class="h-full bg-primary-container rounded-full transition-all duration-500 ease-out" id="step-bar" style="width:20%"></div>')
v.r('type="email" value="hamster.nightly@studio.kr"/>', 'type="email" autocomplete="username"/>')
v.r('''<span class="material-symbols-outlined absolute right-3.5 text-primary text-[20px]" style="font-variation-settings: 'FILL' 1;">check_circle</span>
</div>
<p class="flex items-center gap-1 text-primary font-label-sm text-label-sm mt-0.5 pl-1">
<span class="material-symbols-outlined text-[14px]">check</span>
        사용 가능한 이메일 형식입니다.''', '''<span class="hidden material-symbols-outlined absolute right-3.5 text-primary text-[20px]" id="email-ok-icon" style="font-variation-settings: 'FILL' 1;">check_circle</span>
</div>
<p class="hidden flex items-center gap-1 text-primary font-label-sm text-label-sm mt-0.5 pl-1" id="email-ok">
<span class="material-symbols-outlined text-[14px]">check</span>
        사용 가능한 이메일 형식입니다.''')
v.r('<span class="text-secondary font-label-sm text-label-sm">안전 등급: 매우 높음</span>', '<span class="text-secondary font-label-sm text-label-sm" data-k="strength"></span>')
v.r('id="user-password" placeholder="비밀번호 입력" type="text" value="P@ssw0rd2025"/>', 'id="user-password" placeholder="비밀번호 입력" type="password" autocomplete="new-password"/>')
v.r('''<button aria-label="Toggle password visibility" class="w-9 h-9 absolute right-1.5''', '''<button aria-label="Toggle password visibility" id="togglePassword" class="w-9 h-9 absolute right-1.5''')
v.r('<span class="material-symbols-outlined text-[20px]">visibility</span>', '<span class="material-symbols-outlined text-[20px]" id="pwdIcon">visibility_off</span>')
for rule, label in (("length", "8자 이상"), ("upper", "영문 대문자 포함"), ("lower", "영문 소문자 포함"), ("digit", "숫자 포함"), ("special", "특수문자 (!@#$%^&amp;*) 포함")):
    v.rx(r'<div class="flex items-center gap-1\.5 text-primary font-label-sm text-label-sm( col-span-2)?">\s*<span class="material-symbols-outlined text-\[15px\]" style="font-variation-settings: \'FILL\' 1;">check_circle</span>\s*<span>' + re.escape(label) + '</span>',
         lambda m, rule=rule, label=label: f'<div class="flex items-center gap-1.5 text-on-surface-variant font-label-sm text-label-sm{m.group(1) or ""}" data-rule="{rule}">\n<span class="material-symbols-outlined text-[15px]" style="font-variation-settings: \'FILL\' 1;">radio_button_unchecked</span>\n<span>{label}</span>')
v.r('id="user-password-confirm" placeholder="비밀번호 재입력" type="password" value="P@ssw0rd2025"/>', 'id="user-password-confirm" placeholder="비밀번호 재입력" type="password" autocomplete="new-password"/>')
v.r('''<span class="material-symbols-outlined absolute right-3.5 text-primary text-[20px]" style="font-variation-settings: 'FILL' 1;">check_circle</span>
</div>
<p class="flex items-center gap-1 text-primary font-label-sm text-label-sm mt-0.5 pl-1">
<span class="material-symbols-outlined text-[14px]">check</span>
        두 비밀번호가 완벽히 일치합니다.''', '''<span class="hidden material-symbols-outlined absolute right-3.5 text-primary text-[20px]" id="match-icon" style="font-variation-settings: 'FILL' 1;">check_circle</span>
</div>
<p class="hidden flex items-center gap-1 text-primary font-label-sm text-label-sm mt-0.5 pl-1" id="match-hint">
<span class="material-symbols-outlined text-[14px]" id="match-hint-icon">check</span>
        <span data-k="match">두 비밀번호가 완벽히 일치합니다.</span>''')
# invite code field (same component as the email field), shown only when joining a household
v.r('<!-- Password Input Field -->', '''<!-- Invite Code Field (family join) -->
<div class="hidden flex flex-col gap-1.5" id="invite-field">
<label class="font-label-md text-label-md text-on-surface-variant flex items-center justify-between" for="invite-code">
<span>가족 초대 코드</span>
<span class="text-primary font-label-sm text-label-sm">필수 항목</span>
</label>
<div class="relative flex items-center">
<span class="material-symbols-outlined absolute left-3.5 text-on-surface-variant text-[20px]">diversity_1</span>
<input class="w-full h-12 pl-11 pr-10 rounded-xl bg-surface-container text-on-surface placeholder:text-outline font-body-md text-body-md uppercase tracking-widest focus:outline-none focus:bg-surface-container-high transition-all" id="invite-code" placeholder="8자리 코드" type="text" maxlength="8" autocomplete="off"/>
</div>
</div>
<!-- Password Input Field -->''')
# agreements: real checkboxes styled with the Stitch boxes
v.r('''<label class="flex items-center justify-between cursor-pointer select-none group py-1">
<div class="flex items-center gap-3">
<div class="w-6 h-6 rounded-lg bg-primary flex items-center justify-center transition-transform active:scale-95 shadow-sm">''', '''<label class="flex items-center justify-between cursor-pointer select-none group py-1">
<div class="flex items-center gap-3">
<input class="peer sr-only" id="agree-all" type="checkbox"/>
<div class="w-6 h-6 rounded-lg bg-surface-container-high text-transparent peer-checked:bg-primary peer-checked:text-on-primary flex items-center justify-center transition-transform active:scale-95 shadow-sm">''')
v.r('<span class="material-symbols-outlined text-on-primary text-[18px] font-bold">check</span>', '<span class="material-symbols-outlined text-[18px] font-bold">check</span>')
v.r('전체 동의 (선택 포함)', '전체 동의')
items = (("terms", "[필수] 서비스 이용약관 동의", "/terms"), ("privacy", "[필수] 개인정보 수집 및 이용 동의", "/privacy"),
         ("camera", "[필수] 홈 캠 촬영 및 클라우드 저장 안내 확인", "/privacy#camera"))
for key, label, href in items:
    new_label = label.replace("클라우드 저장", "로컬 저장")
    v.r(f'''<label class="flex items-center gap-3 cursor-pointer flex-1 min-w-0">
<div class="w-5 h-5 rounded-md bg-primary/20 text-primary flex items-center justify-center">
<span class="material-symbols-outlined text-[16px]">check</span>
</div>
<span class="font-body-md text-body-md text-on-surface truncate">{label}</span>
</label>
<button class="px-2 py-1 text-secondary hover:text-primary transition-colors font-label-md text-label-md shrink-0 flex items-center gap-0.5" type="button">''', f'''<label class="flex items-center gap-3 cursor-pointer flex-1 min-w-0">
<input class="peer sr-only agree" id="agree-{key}" type="checkbox"/>
<div class="w-5 h-5 rounded-md bg-surface-container-high text-transparent peer-checked:bg-primary/20 peer-checked:text-primary flex items-center justify-center">
<span class="material-symbols-outlined text-[16px]">check</span>
</div>
<span class="font-body-md text-body-md text-on-surface truncate">{new_label}</span>
</label>
<a class="px-2 py-1 text-secondary hover:text-primary transition-colors font-label-md text-label-md shrink-0 flex items-center gap-0.5" href="{href}" target="_blank" rel="noopener">''')
v.r('''<span>보기</span>
<span class="material-symbols-outlined text-[16px]">chevron_right</span>
</button>''', '''<span>보기</span>
<span class="material-symbols-outlined text-[16px]">chevron_right</span>
</a>''', 3)
v.r('기기 간 영상 피드는 종단간 암호화(E2EE)로 안전하게 보호됩니다.', '영상은 집 PC에만 저장되고, Tailscale 암호화 사설망으로만 전달됩니다.')
v.r('<!-- Next Submission CTA Button -->', ERR.format(id="signup-error") + '\n<!-- Next Submission CTA Button -->')
v.r('''<button class="w-full h-12 rounded-xl bg-primary text-on-primary font-headline-sm text-headline-sm flex items-center justify-center gap-2 hover:bg-primary-fixed transition-all active:scale-[0.99] shadow-lg shadow-primary/10" type="button">
<span>다음 (2/5 단계)</span>''', '''<button class="w-full h-12 rounded-xl bg-primary text-on-primary font-headline-sm text-headline-sm flex items-center justify-center gap-2 hover:bg-primary-fixed transition-all active:scale-[0.99] shadow-lg shadow-primary/10 disabled:opacity-40" id="btn-next" type="button" disabled>
<span data-k="cta">다음 (2/5 단계)</span>''')
v.save()

# ---- verify
v = View("verify")
v.r(AVATAR, AVATAR_LINK.replace('href="#status"', 'href="#welcome"'))
v.r('<span class="tracking-widest font-mono text-secondary">2 / 5 단계</span>', '<span class="tracking-widest font-mono text-secondary" data-k="step">2 / 5 단계</span>')
v.r('style="width: 40%;"></div>', 'id="step-bar" style="width: 40%;"></div>')
v.r('<span class="font-label-lg text-label-lg text-on-surface truncate font-mono">bory_mom@homestudio.kr</span>', '<span class="font-label-lg text-label-lg text-on-surface truncate font-mono" data-k="email"></span>')
v.r('''<button class="shrink-0 h-9 px-3 rounded-full bg-surface-container-high''', '''<button id="btn-change" class="shrink-0 h-9 px-3 rounded-full bg-surface-container-high''')
v.rx(r'<div class="flex items-center justify-between w-full max-w-\[340px\] gap-2">.*?</div>\s*<!-- Hidden Native Input', '<div class="flex items-center justify-between w-full max-w-[340px] gap-2 cursor-text" id="code-boxes"></div>\n<!-- Hidden Native Input')
v.r('<input aria-label="6자리 이메일 인증번호" class="opacity-0 absolute pointer-events-none -z-10" id="authCodeInput" inputmode="numeric" maxlength="6" type="number" value="4820"/>',
    '<input aria-label="6자리 이메일 인증번호" class="opacity-0 absolute -z-10 w-px h-px" id="authCodeInput" inputmode="numeric" maxlength="6" type="text" autocomplete="one-time-code"/>')
v.r('id="timerClock">02:48</span>', 'id="timerClock">10:00</span>')
v.r('''        스팸 메일함으로 분류되었을 수 있으니 메일함을 확인해주세요.''', '''        <span data-k="mail_note">스팸 메일함으로 분류되었을 수 있으니 메일함을 확인해주세요.</span>''')
v.r('<span class="text-label-sm font-label-sm text-on-surface-variant">보리(골든 햄스터)가 쳇바퀴 옆에서 기다려요</span>', '<span class="text-label-sm font-label-sm text-on-surface-variant" data-k="pet_note">햄스터가 쳇바퀴 옆에서 기다려요</span>')
v.r('<!-- Primary Sticky Bottom CTA -->', ERR.format(id="verify-error") + '\n<!-- Primary Sticky Bottom CTA -->')
v.r('<span>인증 완료 및 다음 (3/5)</span>', '<span data-k="cta">인증 완료 및 다음 (3/5)</span>')
v.save()

# ---- pet (step 3)
v = View("pet")
v.r(AVATAR, AVATAR_LINK)
v.r('type="text" value="보리 (Bory)"/>', 'type="text" maxlength="10"/>')
v.r('''<div class="absolute right-3.5 flex items-center justify-center text-primary pointer-events-none">''', '''<div class="hidden absolute right-3.5 flex items-center justify-center text-primary pointer-events-none" id="name-ok-icon">''')
v.r('<div class="flex items-center gap-1 text-primary font-body-sm text-body-sm mt-0.5">', '<div class="hidden flex items-center gap-1 text-primary font-body-sm text-body-sm mt-0.5" id="name-ok">')
v.r('<span class="flex items-center gap-2">\n<span class="w-2 h-2 rounded-full bg-primary animate-pulse"></span>\n            골든 햄스터\n          </span>', '<span class="flex items-center gap-2">\n<span class="w-2 h-2 rounded-full bg-primary animate-pulse"></span>\n            골든 햄스터\n          </span>')
for sp in ("골든 햄스터", "드워프 햄스터", "로보로브스키", "기타 소동물"):
    v.rx(r'(<button aria-checked="(?:true|false)" class="species-chip)((?:(?!</button>).)*?' + sp + ')', lambda m, sp=sp: m.group(1).replace('class="species-chip', f'data-species="{sp}" class="species-chip') + m.group(2))
v.r('placeholder="YYYY-MM-DD" type="text" value="2023년 5월 12일"/>', 'placeholder="YYYY-MM-DD" type="date"/>')
v.r('''<button class="flex-1 h-full rounded-lg text-on-surface-variant font-label-md text-label-md flex items-center justify-center gap-1 transition-colors hover:text-on-surface" type="button">
<span>남아</span>''', '''<button class="sex-btn flex-1 h-full rounded-lg text-on-surface-variant font-label-md text-label-md flex items-center justify-center gap-1 transition-colors hover:text-on-surface" data-sex="male" type="button">
<span>남아</span>''')
v.r('''<button class="flex-1 h-full rounded-lg bg-surface-container-high text-primary font-label-md text-label-md flex items-center justify-center gap-1 shadow-sm transition-colors" type="button">''', '''<button class="sex-btn flex-1 h-full rounded-lg text-on-surface-variant font-label-md text-label-md flex items-center justify-center gap-1 transition-colors hover:text-on-surface" data-sex="female" type="button">''')
v.r('placeholder="0" type="text" value="125"/>', 'placeholder="0" type="text" inputmode="decimal"/>')
v.r('<!-- Sticky CTA Anchor -->', ERR.format(id="pet-error") + '\n<!-- Sticky CTA Anchor -->')
v.r('<button aria-label="반려동물 사진 변경" class="absolute', '<input type="file" accept="image/jpeg,image/png" id="pet-photo" class="hidden"/><button aria-label="반려동물 사진 변경" id="btn-photo" class="absolute')
v.r('<img class="w-full h-full object-cover" src="assets/art-pet.jpg"/>', '<img class="w-full h-full object-cover" id="pet-avatar" src="assets/art-pet.jpg"/>')
v.r('<span>사진 등록</span>', '<span data-k="photo_label">사진 등록</span>')
# settings mode (opened from status): progress hidden, CTA becomes save
v.r('<!-- Progress Header Indicator -->\n<div class="flex flex-col gap-space-xs mt-2 mb-6">', '<!-- Progress Header Indicator -->\n<div class="flex flex-col gap-space-xs mt-2 mb-6" id="onb-progress">')
v.r('<span>다음 (4/5 단계)</span>\n<span class="material-symbols-outlined text-[18px]">arrow_forward</span>', '<span data-k="next_label">다음 (4/5 단계)</span>\n<span class="material-symbols-outlined text-[18px]" data-k="next_icon">arrow_forward</span>')
v.save()

# ---- schedule (step 4)
v = View("schedule")
v.r(AVATAR, AVATAR_LINK)
v.r('<span class="font-label-sm text-label-sm text-outline mt-0.5">다음 날 11:59까지 1일로 집계</span>', '<span class="font-label-sm text-label-sm text-outline mt-0.5" id="time-until">다음 날 11:59까지 1일로 집계</span>')
v.r('<span class="font-label-md text-label-md text-primary font-semibold">23:00 ~ 07:00</span>', '<span class="font-label-md text-label-md text-primary font-semibold">23:00 ~ 07:00</span>')
v.r('<!-- Sticky Bottom Navigation CTA Area -->', ERR.format(id="schedule-error") + '\n<!-- Sticky Bottom Navigation CTA Area -->')
v.r('''<button class="w-full h-14 rounded-full bg-primary text-on-primary font-label-lg text-label-lg font-semibold flex items-center justify-center gap-2 shadow-[0_12px_28px_rgba(90,240,179,0.25)] hover:bg-primary-fixed active:scale-[0.98] transition-all" type="button">''', '''<button class="w-full h-14 rounded-full bg-primary text-on-primary font-label-lg text-label-lg font-semibold flex items-center justify-center gap-2 shadow-[0_12px_28px_rgba(90,240,179,0.25)] hover:bg-primary-fixed active:scale-[0.98] transition-all" id="btn-next" type="button">''')
v.save()

# ---- camera (step 5)
v = View("camera")
v.r(AVATAR, AVATAR_LINK)
v.r('<img class="w-full h-full object-cover opacity-85" src=""', '<img class="w-full h-full object-cover opacity-85" id="cam-img" src=""')
v.r('<span class="font-label-sm text-label-sm text-primary tracking-wide">LIVE · IR 야간 모드</span>', '<span class="font-label-sm text-label-sm text-primary tracking-wide" data-k="cam_badge">LIVE · IR 야간 모드</span>')
v.r('''        1080p 30fps''', '''        <span data-k="cam_spec">1080p 30fps</span>''')
v.r('<span class="font-label-lg text-label-lg text-primary">카메라 연결됨 (정상 작동 중)</span>', '<span class="font-label-lg text-label-lg text-primary" data-k="cam_status">카메라 연결됨 (정상 작동 중)</span>')
v.r('''        신호 강도: 우수 (-42dBm) · 펌웨어 v2.4.1''', '''        <span data-k="cam_detail">신호 강도: 우수 (-42dBm) · 펌웨어 v2.4.1</span>''')
v.r('집사가 케이지를 청소하거나 방에 머무를 때는 원터치로 렌즈 물리 셔터를 닫고 스트리밍을 정지할 수 있어요.', '집사가 케이지를 청소하거나 방에 머무를 때는 카메라 프라이버시 모드(렌즈 수납)로 촬영과 저장을 멈출 수 있어요.')
v.r('<!-- Sticky-styled Bottom CTA Container -->', ERR.format(id="camera-error") + '\n<!-- Sticky-styled Bottom CTA Container -->')
v.save()

# ---- done
v = View("done")
v.r(AVATAR, AVATAR_LINK)
v.r('''      이제 '보리'의 소중한 밤과 낮을''', '''      이제 '<span data-k="pet_name">보리</span>'의 소중한 밤과 낮을''')
v.r('''<span class="font-label-lg text-label-lg text-on-surface font-medium">보리 <span class="font-body-sm text-body-sm text-on-surface-variant">(골든 햄스터, 125g)</span></span>''', '''<span class="font-label-lg text-label-lg text-on-surface font-medium"><span data-k="pet_name">보리</span> <span class="font-body-sm text-body-sm text-on-surface-variant" data-k="pet_detail">(골든 햄스터, 125g)</span></span>''')
v.r('<span class="font-label-lg text-label-lg text-on-surface font-medium">낮 12:00 ~ 익일 12:00</span>', '<span class="font-label-lg text-label-lg text-on-surface font-medium" data-k="care_cycle">낮 12:00 ~ 익일 12:00</span>')
v.r('<span class="font-label-lg text-label-lg text-on-surface font-medium">HomeStudio 캠 Pro</span>', '<span class="font-label-lg text-label-lg text-on-surface font-medium">TVS-W1000</span>')
v.r('<span class="font-label-sm text-label-sm font-semibold">연결 완료</span>', '<span class="font-label-sm text-label-sm font-semibold" data-k="cam_short">연결 완료</span>')
v.r('<span class="font-label-lg text-label-lg text-on-surface font-medium">가족 1인 초대됨</span>', '<span class="font-label-lg text-label-lg text-on-surface font-medium" data-k="family">가족 1인 초대됨</span>')
v.r('<span class="font-label-sm text-label-sm text-secondary bg-surface-container px-2 py-0.5 rounded-md">연동 대기 중</span>', '<span class="font-label-sm text-label-sm text-secondary bg-surface-container px-2 py-0.5 rounded-md">상태 탭에서 초대</span>')
v.r('''          보리가 쳇바퀴를 돌리기 시작하면 스마트 센서가 첫 야간 리포트를 자동으로 작성합니다.''', '''          <span data-k="pet_name">보리</span>가 움직이기 시작하면 카메라가 활동 구간과 클립을 자동으로 기록합니다.''')
v.r('''onclick="window.location.href='#home'" type="button">''', '''id="btn-home" type="button">''')
v.save()

# ---- pin: quick unlock of a remembered device (and "pinset" variant for setting it)
def pin_view(mode):
    v = View("pin")
    v.r('      가구 전용 간편 PIN 4자리를 입력해주세요.', '      <span data-k="pin_sub">가구 전용 간편 PIN 4~6자리를 입력해주세요.</span>')
    v.rx(r'<div class="flex items-center justify-center gap-4 py-3 mb-6 w-full bg-surface-container-low rounded-2xl">.*?</div>\s*<!-- Cozy', '<div class="flex items-center justify-center gap-4 py-3 mb-6 w-full bg-surface-container-low rounded-2xl" id="pin-dots"></div>\n<!-- Cozy')
    # bottom-left key (Stitch: biometric) becomes the confirm key; Face ID stays a placeholder
    v.r('aria-label="생체 인증 바로 실행" class="h-14 rounded-full bg-surface-container-low hover:bg-surface-container-high text-primary', 'aria-label="확인" class="h-14 rounded-full bg-primary-container/20 hover:bg-surface-container-high text-primary')
    v.r('<span class="material-symbols-outlined text-[26px]">familiar_face_and_zone</span>\n</button>\n<!-- 0 -->', '<span class="material-symbols-outlined text-[26px]">check</span>\n</button>\n<!-- 0 -->')
    v.r('id="faceid-btn" type="button">', 'id="faceid-btn" type="button" disabled>')
    v.r('<span class="">Face ID로 빠른 로그인</span>', '<span class="">Face ID로 빠른 로그인 (준비 중)</span>')
    v.r('<!-- Face ID Action Banner -->', ERR.format(id="pin-error").replace('mt-1', 'mb-3 w-full') + '\n<!-- Face ID Action Banner -->')
    v.r('''<button class="flex items-center gap-1.5 text-secondary hover:text-primary transition py-1 text-center font-label-md text-label-md" type="button">''', '''<button class="flex items-center gap-1.5 text-secondary hover:text-primary transition py-1 text-center font-label-md text-label-md" id="btn-invite" type="button">''')
    v.r('''<button class="text-on-surface-variant hover:text-on-surface transition font-label-sm text-label-sm" type="button">
        PIN 번호를 잊으셨나요?''', '''<button class="text-on-surface-variant hover:text-on-surface transition font-label-sm text-label-sm" id="btn-forgot" type="button">
        PIN 번호를 잊으셨나요?''')
    v.r('''<button class="text-on-surface-variant hover:text-on-surface transition font-label-sm text-label-sm" type="button">
        일반 계정 로그인''', '''<button class="text-on-surface-variant hover:text-on-surface transition font-label-sm text-label-sm" id="btn-login" type="button">
        일반 계정 로그인''')
    v.r('‘모찌’의 쳇바퀴 룸 센서 대기 중', '<span data-k="toast">HomeStudio 카메라 대기 중</span>')
    if mode == "pinset":
        v.r('<h2 class="font-headline-sm text-headline-sm text-on-surface">HomeStudio 접속</h2>', '<h2 class="font-headline-sm text-headline-sm text-on-surface">간편 PIN 설정</h2>')
        # current password (login field component) is required to set a PIN
        v.r('<!-- PIN Visual Dots Display -->', '''<div class="relative flex items-center w-full mb-4">
<div class="absolute left-3.5 flex items-center justify-center pointer-events-none text-on-surface-variant"><span class="material-symbols-outlined text-[20px]">lock</span></div>
<input class="w-full h-13 py-3.5 pl-11 pr-4 rounded-xl bg-surface-container-low text-on-surface font-body-md text-body-md focus:outline-none focus:bg-surface-container-high transition-all tracking-wider" id="pin-password" placeholder="현재 비밀번호" type="password" autocomplete="current-password"/>
</div>
<!-- PIN Visual Dots Display -->''')
    v.save(mode)

pin_view("pin")
pin_view("pinset")

# ---- password change (no Stitch screen: built from the reset screen, which is built from login)
pw = View("login")
pw.s = open("/workspace/port/out/views/forgot.html").read()
pw.name = "password"
pw.r('Password Reset</h1>', 'Change Password</h1>')
pw.r('<span class="font-label-sm text-label-sm text-on-surface-variant">계정 복구</span>', '<span class="font-label-sm text-label-sm text-on-surface-variant">계정 보안</span>')
pw.r('''비밀번호를
다시 설정해주세요</h2>''', '''새 비밀번호로
변경할게요</h2>''')
pw.r('가입한 이메일로 6자리 재설정 코드를 보내드려요.</p>', '변경하면 이 기기를 제외한 다른 기기는 모두 로그아웃돼요.</p>')
pw.r('<form class="flex flex-col gap-4" id="reset-form" novalidate>', '<form class="flex flex-col gap-4" id="password-form" novalidate>')
pw.rx(r'<!-- Email Field.*?(?=<div class="flex flex-col gap-1.5 reset-step2 hidden">)', '')
pw.r('<label class="font-label-md text-label-md text-on-surface-variant" for="reset-code">재설정 코드 (6자리)</label>', '<label class="font-label-md text-label-md text-on-surface-variant" for="reset-code">현재 비밀번호</label>')
pw.r('<span class="material-symbols-outlined text-[20px]">pin</span>', '<span class="material-symbols-outlined text-[20px]">key</span>')
pw.r('id="reset-code" placeholder="000000" type="text" inputmode="numeric" maxlength="6" autocomplete="one-time-code"/>', 'id="reset-code" placeholder="현재 비밀번호" type="password" autocomplete="current-password"/>')
pw.s = pw.s.replace(' reset-step2 hidden', '').replace('<div class="reset-step2 hidden">', '<div>')
pw.r('<span id="reset-cta">재설정 코드 받기</span>', '<span id="reset-cta">비밀번호 변경</span>')
pw.r('<span class="font-body-md text-body-md text-on-surface-variant">비밀번호가 기억나셨나요?</span>', '<span class="font-body-md text-body-md text-on-surface-variant">변경하지 않으려면</span>')
pw.r('''id="btn-login" type="button">
      로그인하기''', '''id="btn-login" type="button">
      돌아가기''')
pw.save()
print("auth views ok")
