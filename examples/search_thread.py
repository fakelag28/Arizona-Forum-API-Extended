import arz_api_extended as arz_api
import json

cookies = {"xf_user": "",
           "xf_tfa_trust": "",
           "xf_session": ""}

forum_api = arz_api.ArizonaAPI(user_agent="user_agent", cookie=cookies)

threads = forum_api.search_threads('Nicolas_Reed') # Получаем список тем по запросу "Nicolas_Reed"
print(json.dumps(threads, indent=4, ensure_ascii=False)) # Выводим в формате JSON в удобном для просматривания виде