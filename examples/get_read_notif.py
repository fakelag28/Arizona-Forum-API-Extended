import arz_api_extended as arz_api
import json

cookies = {"xf_user": "",
           "xf_tfa_trust": "",
           "xf_session": ""}

forum_api = arz_api.ArizonaAPI(user_agent="user_agent", cookie=cookies)

notifications = forum_api.get_notifications() # Получаем список уведомлений
print(json.dumps(notifications, indent=4, ensure_ascii=False)) # Выводим уведомления в формате JSON в удобном для просматривания виде
forum_api.mark_notifications_read([int(notifications[0]['id'])]) # Пометит прочитанным первое уведомление