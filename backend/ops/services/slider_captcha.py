import secrets

from django.core import signing
from django.core.cache import cache


SLIDER_CHALLENGE_SALT = 'ongrid-slider-captcha-challenge'
SLIDER_VERIFICATION_SALT = 'ongrid-slider-captcha-verification'
SLIDER_MAX_AGE = 300
SLIDER_CANVAS_WIDTH = 320
SLIDER_CANVAS_HEIGHT = 140
SLIDER_PIECE_SIZE = 44
SLIDER_TOLERANCE = 5
SLIDER_MIN_ELAPSED_MS = 350


def _challenge_cache_key(challenge_id):
    """生成拖拽挑战缓存键。

    参数：`challenge_id` 为随机挑战编号。
    返回：仅用于服务端缓存的挑战键。
    副作用：不读取或修改缓存。
    """
    return f'login-slider:challenge:{challenge_id}'


def _verification_cache_key(verification_id):
    """生成拖拽验证成功凭证缓存键。

    参数：`verification_id` 为随机验证编号。
    返回：仅用于服务端缓存的验证键。
    副作用：不读取或修改缓存。
    """
    return f'login-slider:verification:{verification_id}'


def issue_slider_challenge(ip_address):
    """签发绑定来源地址的短期拖拽拼图挑战。

    参数：`ip_address` 为请求来源地址。
    返回：前端绘图参数和不暴露服务端缓存状态的签名挑战令牌。
    副作用：向默认缓存写入一条五分钟有效的挑战状态。
    """
    challenge_id = secrets.token_urlsafe(18)
    target_x = secrets.randbelow(171) + 96
    target_y = secrets.randbelow(47) + 38
    scene_seed = secrets.randbelow(2_147_483_647)
    cache.set(
        _challenge_cache_key(challenge_id),
        {'ip_address': str(ip_address or ''), 'target_x': target_x},
        timeout=SLIDER_MAX_AGE,
    )
    token = signing.dumps({'challenge_id': challenge_id}, salt=SLIDER_CHALLENGE_SALT)
    return {
        'challenge_token': token,
        'scene_seed': scene_seed,
        'target_x': target_x,
        'target_y': target_y,
        'canvas_width': SLIDER_CANVAS_WIDTH,
        'canvas_height': SLIDER_CANVAS_HEIGHT,
        'piece_size': SLIDER_PIECE_SIZE,
        'expires_in': SLIDER_MAX_AGE,
    }


def verify_slider_challenge(token, offset_x, elapsed_ms, ip_address):
    """校验拖拽位置并签发一次性登录验证凭证。

    参数：`token` 为挑战令牌；`offset_x` 为用户释放时的横向位置；
    `elapsed_ms` 为本次拖拽耗时；`ip_address` 为请求来源地址。
    返回：验证成功时返回签名凭证，失败时返回空字符串。
    副作用：读取并删除挑战缓存；成功时新增一条验证凭证缓存。
    """
    try:
        payload = signing.loads(token, salt=SLIDER_CHALLENGE_SALT, max_age=SLIDER_MAX_AGE)
        challenge_id = str(payload.get('challenge_id') or '')
        submitted_offset = int(offset_x)
        submitted_elapsed = int(elapsed_ms)
    except (signing.BadSignature, signing.SignatureExpired, TypeError, ValueError):
        return ''
    if not challenge_id:
        return ''
    cache_key = _challenge_cache_key(challenge_id)
    challenge = cache.get(cache_key)
    cache.delete(cache_key)
    if not isinstance(challenge, dict):
        return ''
    if challenge.get('ip_address') != str(ip_address or ''):
        return ''
    if submitted_elapsed < SLIDER_MIN_ELAPSED_MS or submitted_elapsed > SLIDER_MAX_AGE * 1000:
        return ''
    if abs(submitted_offset - int(challenge.get('target_x', -100))) > SLIDER_TOLERANCE:
        return ''
    verification_id = secrets.token_urlsafe(18)
    cache.set(
        _verification_cache_key(verification_id),
        {'ip_address': str(ip_address or '')},
        timeout=SLIDER_MAX_AGE,
    )
    return signing.dumps({'verification_id': verification_id}, salt=SLIDER_VERIFICATION_SALT)


def consume_slider_verification(token, ip_address):
    """消费拖拽验证成功凭证并阻止重复用于登录。

    参数：`token` 为验证成功凭证；`ip_address` 为当前登录来源地址。
    返回：凭证有效、来源一致且未使用时返回真，否则返回假。
    副作用：读取并删除验证缓存，使凭证只能消费一次。
    """
    try:
        payload = signing.loads(token, salt=SLIDER_VERIFICATION_SALT, max_age=SLIDER_MAX_AGE)
        verification_id = str(payload.get('verification_id') or '')
    except (signing.BadSignature, signing.SignatureExpired):
        return False
    if not verification_id:
        return False
    cache_key = _verification_cache_key(verification_id)
    verification = cache.get(cache_key)
    cache.delete(cache_key)
    return isinstance(verification, dict) and verification.get('ip_address') == str(ip_address or '')
