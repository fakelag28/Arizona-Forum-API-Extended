import arz_api_extended as arz_api
import json

cookies = {"xf_user": "",
           "xf_tfa_trust": "",
           "xf_session": ""}

forum_api = arz_api.ArizonaAPI(user_agent="user_agent", cookie=cookies)

notifications = forum_api.get_notifications()
forum_api.mark_notifications_read([int(notifications[0]['id'])]) # Пометит прочитанным первое уведомление
print(json.dumps(notifications, indent=4, ensure_ascii=False))