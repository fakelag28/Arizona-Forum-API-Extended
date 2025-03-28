from bs4 import BeautifulSoup
from re import compile, findall
from requests import session, Response
from html import unescape

from arz_api_extended.consts import MAIN_URL, ROLE_COLOR
from arz_api_extended.bypass_antibot import bypass

from arz_api_extended.exceptions import IncorrectLoginData, ThisIsYouError
from arz_api_extended.models.other import Statistic
from arz_api_extended.models.post_object import Post, ProfilePost
from arz_api_extended.models.member_object import Member, CurrentMember
from arz_api_extended.models.thread_object import Thread
from arz_api_extended.models.category_object import Category


class ArizonaAPI:
    def __init__(self, user_agent: str, cookie: dict, do_bypass: bool = True) -> None:
        self.user_agent = user_agent
        self.cookie = cookie
        self.session = session()
        self.session.headers = {"user-agent": user_agent}
        self.session.cookies.update(cookie)

        if do_bypass:
            name, code = str(bypass(user_agent)).split('=')
            self.session.cookies.set(name, code)

        if BeautifulSoup(self.session.get(f"{MAIN_URL}").content, 'lxml').find('html')['data-logged-in'] == "false":
            raise IncorrectLoginData

    
    def logout(self):
        """Закрыть сессию"""

        return self.session.close()

    
    @property
    def current_member(self) -> CurrentMember:
        """Объект текущего пользователя"""

        content = BeautifulSoup(self.session.get(f"{MAIN_URL}/account").content, 'lxml')
        user_id = int(content.find('span', {'class': 'avatar--xxs'})['data-user-id'])
        member_info = self.get_member(user_id)

        return CurrentMember(self, user_id, member_info.username, member_info.user_title, member_info.avatar, member_info.roles, member_info.messages_count, member_info.reactions_count, member_info.trophies_count)

    @property
    def token(self) -> str:
        """Получить токен CSRF"""
        return BeautifulSoup(self.session.get(f"{MAIN_URL}/help/terms/").content, 'lxml').find('html')['data-csrf']


    def get_category(self, category_id: int) -> Category:
        """Найти раздел по ID"""

        request = self.session.get(f"{MAIN_URL}/forums/{category_id}?_xfResponseType=json&_xfToken={self.token}").json()
        if request['status'] == 'error':
            return None

        content = unescape(request['html']['content'])
        content = BeautifulSoup(content, 'lxml')

        title = unescape(request['html']['title'])
        try: pages_count = int(content.find_all('li', {'class': 'pageNav-page'})[-1].text)
        except IndexError: pages_count = 1

        return Category(self, category_id, title, pages_count)
    
    
    def get_member(self, user_id: int) -> Member:
        """Найти пользователя по ID (возвращает либо Member, либо None (если профиль закрыт / не существует))"""

        request = self.session.get(f"{MAIN_URL}/members/{user_id}?_xfResponseType=json&_xfToken={self.token}").json()
        if request['status'] == 'error':
            return None

        content = unescape(request['html']['content'])
        content = BeautifulSoup(content, 'lxml')

        username = unescape(request['html']['title'])

        username_class = content.find('span', class_='username')

        if username_class:
            for style in ROLE_COLOR:
                if style in str(username_class):
                    username_color = ROLE_COLOR[style]
                    break
            else:
                username_color = '#fff'

        roles = []
        for i in content.find('div', {'class': 'memberHeader-banners'}).children:
            if i.text != '\n': roles.append(i.text)

        try: user_title = content.find('span', {'class': 'userTitle'}).text
        except AttributeError: user_title = None
        try: avatar = MAIN_URL + content.find('a', {'class': 'avatar avatar--l'})['href']
        except TypeError: avatar = None

        messages_count = int(content.find('a', {'href': f'/search/member?user_id={user_id}'}).text.strip().replace(',', ''))
        reactions_count = int(content.find('dl', {'class': 'pairs pairs--rows pairs--rows--centered'}).find('dd').text.strip().replace(',', ''))
        trophies_count = int(content.find('a', {'href': f'/members/{user_id}/trophies'}).text.strip().replace(',', ''))
        
        return Member(self, user_id, username, user_title, avatar, roles, messages_count, reactions_count, trophies_count, username_color)
    

    def get_thread(self, thread_id: int):
        request = self.session.get(f"{MAIN_URL}/threads/{thread_id}/page-1?_xfResponseType=json&_xfToken={self.token}").json()
        if request['status'] == 'error':
            return None
        
        if request.get('redirect') is not None:
            return self.get_thread(request['redirect'].strip(MAIN_URL).split('/')[1])

        content = unescape(request['html']['content'])
        content_h1 = unescape(request['html']['h1'])
        content = BeautifulSoup(content, 'lxml')
        content_h1 = BeautifulSoup(content_h1, 'lxml')

        creator_id = content.find('a', {'class': 'username'})
        try: creator = self.get_member(int(creator_id['data-user-id']))
        except: creator = Member(self, int(creator_id['data-user-id']), content.find('a', {'class': 'username'}).text, None, None, None, None, None, None, None)
        
        create_date = int(content.find('time')['data-time'])
        
        try:
            prefix = content_h1.find('span', {'class': 'label'}).text
            title = content_h1.text.strip(prefix).strip()

        except AttributeError:
            prefix = ""
            title = content_h1.text
        thread_content_html = content.find('div', {'class': 'bbWrapper'})
        thread_content = thread_content_html.text
        
        try: pages_count = int(content.find_all('li', {'class': 'pageNav-page'})[-1].text)
        except IndexError: pages_count = 1

        is_closed = False
        if content.find('dl', {'class': 'blockStatus'}): is_closed = True
        thread_post_id = content.find('article', {'id': compile('js-post-*')})['id'].strip('js-post-')

        return Thread(self, thread_id, creator, create_date, title, prefix, thread_content, thread_content_html, pages_count, thread_post_id, is_closed)


    def get_post(self, post_id: int) -> Post:
        """Найти пост по ID (Post если существует, None - удален / нет доступа)"""

        content = BeautifulSoup(self.session.get(f"{MAIN_URL}/posts/{post_id}").content, 'lxml')
        post = content.find('article', {'id': f'js-post-{post_id}'})
        if post is None:
            return None

        try: creator = self.get_member(int(post.find('a', {'data-xf-init': 'member-tooltip'})['data-user-id']))
        except:
            user_info = post.find('a', {'data-xf-init': 'member-tooltip'})
            creator = Member(self, int(user_info['data-user-id']), user_info.text, None, None, None, None, None, None, None)

        thread = self.get_thread(int(content.find('html')['data-content-key'].strip('thread-')))
        create_date = int(post.find('time', {'class': 'u-dt'})['data-time'])
        bb_content = post.find('div', {'class': 'bbWrapper'})
        text_content = bb_content.text
        return Post(self, post_id, creator, thread, create_date, bb_content, text_content)


    def get_profile_post(self, post_id: int) -> ProfilePost:
        """Найти сообщение профиля по ID"""

        content = BeautifulSoup(self.session.get(f"{MAIN_URL}/profile-posts/{post_id}").content, 'lxml')
        post = content.find('article', {'id': f'js-profilePost-{post_id}'})
        if post is None:
            return None

        creator = self.get_member(int(post.find('a', {'class': 'username'})['data-user-id']))
        profile = self.get_member(int(content.find('span', {'class': 'username'})['data-user-id']))
        create_date = int(post.find('time')['data-time'])
        bb_content = post.find('div', {'class': 'bbWrapper'})
        text_content = bb_content.text

        return ProfilePost(self, post_id, creator, profile, create_date, bb_content, text_content)

    def get_forum_statistic(self) -> Statistic:
        """Получить статистику форума"""

        content = BeautifulSoup(self.session.get(MAIN_URL).content, 'lxml')
        threads_count = int(content.find('dl', {'class': 'pairs pairs--justified count--threads'}).find('dd').text.replace(',', ''))
        posts_count = int(content.find('dl', {'class': 'pairs pairs--justified count--messages'}).find('dd').text.replace(',', ''))
        users_count = int(content.find('dl', {'class': 'pairs pairs--justified count--users'}).find('dd').text.replace(',', ''))
        last_register_member = self.get_member(int(content.find('dl', {'class': 'pairs pairs--justified'}).find('a')['data-user-id']))

        return Statistic(self, threads_count, posts_count, users_count, last_register_member)
    

    # ---------------================ МЕТОДЫ ОБЪЕКТОВ ====================--------------------


    # CATEGORY
    def create_thread(self, category_id: int, title: str, message_html: str, discussion_type: str = 'discussion', watch_thread: bool = True) -> Response:
        """Создать тему в категории

        Attributes:
            category_id (int): ID категории
            title (str): Название темы
            message_html (str): Содержание темы. Рекомендуется использование HTML
            discussion_type (str): - Тип темы | Возможные варианты: 'discussion' - обсуждение (по умолчанию), 'article' - статья, 'poll' - опрос (необяз.)
            watch_thread (str): - Отслеживать ли тему. По умолчанию True (необяз.)
        
        Returns:
            Объект Response модуля requests

        Todo:
            Cделать возврат ID новой темы
        """

        return self.session.post(f"{MAIN_URL}/forums/{category_id}/post-thread?inline-mode=1", {'_xfToken': self.token, 'title': title, 'message_html': message_html, 'discussion_type': discussion_type, 'watch_thread': int(watch_thread)})
    

    def set_read_category(self, category_id: int) -> Response:
        """Отметить категорию как прочитанную

        Attributes:
            category_id (int): ID категории
        
        Returns:
            Объект Response модуля requests
        """

        return self.session.post(f"{MAIN_URL}/forums/{category_id}/mark-read", {'_xfToken': self.token})
    

    def watch_category(self, category_id: int, notify: str, send_alert: bool = True, send_email: bool = False, stop: bool = False) -> Response:
        """Настроить отслеживание категории

        Attributes:
            category_id (int): ID категории
            notify (str): Объект отслеживания. Возможные варианты: "thread", "message", ""
            send_alert (bool): - Отправлять ли уведомления на форуме. По умолчанию True (необяз.)
            send_email (bool): - Отправлять ли уведомления на почту. По умолчанию False (необяз.)
            stop (bool): - Принудительное завершение отслеживания. По умолчанию False (необяз.)

        Returns:
            Объект Response модуля requests    
        """

        if stop: return self.session.post(f"{MAIN_URL}/forums/{category_id}/watch", {'_xfToken': self.token, 'stop': "1"})
        else: return self.session.post(f"{MAIN_URL}/forums/{category_id}/watch", {'_xfToken': self.token, 'send_alert': int(send_alert), 'send_email': int(send_email), 'notify': notify})


    def get_threads(self, category_id: int, page: int = 1) -> dict:
        """Получить темы из раздела

        Attributes:
            category_id (int): ID категории
            page (int): Cтраница для поиска. По умолчанию 1 (необяз.)
            
        Returns:
            Словарь (dict), состоящий из списков закрепленных ('pins') и незакрепленных ('unpins') тем
        """

        request = self.session.get(f"{MAIN_URL}/forums/{category_id}/page-{page}?_xfResponseType=json&_xfToken={self.token}").json()
        if request['status'] == 'error':
            return None
        
        soup = BeautifulSoup(unescape(request['html']['content']), "lxml")
        result = {'pins': [], 'unpins': []}
        for thread in soup.find_all('div', compile('structItem structItem--thread.*')):
            link = thread.find_all('div', "structItem-title")[0].find_all("a")[-1]
            if len(findall(r'\d+', link['href'])) < 1: continue

            if len(thread.find_all('i', {'title': 'Закреплено'})) > 0: result['pins'].append(int(findall(r'\d+', link['href'])[0]))
            else: result['unpins'].append(int(findall(r'\d+', link['href'])[0]))
        
        return result
    
    def get_threads_extended(self, category_id: int, page: int = 1) -> list:
        """[NEW] Получить темы из раздела на странице, с дополнительной информацией о темах

        Attributes:
            category_id (int): ID категории
            page (int): Cтраница для поиска. По умолчанию 1 (необяз.)
            
        Returns:
            Словарь (dict), состоящий из списков закрепленных ('pins') и незакрепленных ('unpins') тем
        """
        request = self.session.get(f"{MAIN_URL}/forums/{category_id}/page-{page}?_xfResponseType=json&_xfToken={self.token}").json()
        if request['status'] == 'error':
            return None

        soup = BeautifulSoup(unescape(request['html']['content']), "lxml")
        result = []
        seen_thread_ids = set()
        
        for thread in soup.find_all('div', class_=compile('structItem structItem--thread.*')):
            link = thread.find('div', "structItem-title").find_all("a")[-1]
            thread_id = int(findall(r'\d+', link['href'])[0])
            if thread_id in seen_thread_ids:
                continue
            seen_thread_ids.add(thread_id)

            thread_data = {}
            
            username_author = thread.find('div', 'structItem-cell--main').find('div', 'structItem-minor').find('ul', 'structItem-parts').find('a', class_='username')
            thread_data['username_author'] = username_author.text.strip() if username_author else None
            
            thread_data['thread_title'] = link.text.strip()
            
            prefix_label = thread.find('span', class_='label')
            thread_data['prefix'] = prefix_label.text.strip() if prefix_label else None

            if username_author:
                for style in ROLE_COLOR:
                    if style in str(username_author):
                        thread_data['username_author_color'] = ROLE_COLOR[style]
                        break
                else:
                    thread_data['username_author_color'] = '#fff'

            created_date = thread.find('div', 'structItem-cell--main').find('div', 'structItem-minor').find('ul', 'structItem-parts').find('li', 'structItem-startDate').find('time', class_='u-dt').get('data-time')
            thread_data['created_date'] = int(created_date) if created_date else None
            
            last_message_username = thread.find('div', 'structItem-cell--latest').find('div', 'structItem-minor').find(class_=compile('username'))
            thread_data['username_last_message'] = last_message_username.text.strip() if last_message_username else None

            if last_message_username:
                for style in ROLE_COLOR:
                    if style in str(last_message_username):
                        thread_data['username_last_message_color'] = ROLE_COLOR[style]
                        break
                else:
                    thread_data['username_last_message_color'] = '#fff'

            last_message_date = thread.find('div', 'structItem-cell--latest').find('time', class_='structItem-latestDate').get('data-time')
            thread_data['last_message_date'] = int(last_message_date) if last_message_date else None

            thread_data['thread_id'] = thread_id
            thread_data['is_pinned'] = len(thread.find_all('i', {'title': 'Закреплено'})) > 0
            thread_data['is_closed'] = len(thread.find_all('i', {'title': 'Закрыта'})) > 0

            result.append(thread_data)
        
        return result
    
    def get_parent_category_of_category(self, category_id: int) -> Category:
        """Получить родительский раздел раздела

        Attributes:
            category_id (int): ID категории
        
        Returns:
            - Если существует: Объект Catrgory, в котором создан раздел
            - Если не существует: None
        """

        content = BeautifulSoup(self.session.get(f"{MAIN_URL}/forums/{category_id}").content, 'lxml')
        
        parent_category_id = str(content.find('ul', {'class': 'p-breadcrumbs'}).find_all('li')[-1].find('a')['href'].split('/')[2])
        if not parent_category_id.isdigit():
            return None
        
        return self.get_category(parent_category_id)


    def get_categories(self, category_id: int) -> list:
        """Получить дочерние категории из раздела
        
        Attributes:
            category_id (int): ID категории
        
        Returns:
            Список (list), состоящий из ID дочерних категорий раздела
        """

        request = self.session.get(f"{MAIN_URL}/forums/{category_id}/page-1?_xfResponseType=json&_xfToken={self.token}").json()
        if request['status'] == 'error':
            return None
        
        soup = BeautifulSoup(unescape(request['html']['content']), "lxml")
        return [int(findall(r'\d+', category.find("a")['href'])[0]) for category in soup.find_all('div', compile('.*node--depth2 node--forum.*'))]
    

    # MEMBER
    def follow_member(self, member_id: int) -> Response:
        """Изменить статус подписки на пользователя
        
        Attributes:
            member_id (int): ID пользователя
        
        Returns:
            Объект Response модуля requests
        """

        if member_id == self.current_member.id:
            raise ThisIsYouError(member_id)

        return self.session.post(f"{MAIN_URL}/members/{member_id}/follow", {'_xfToken': self.token})
    

    def ignore_member(self, member_id: int) -> Response:
        """Изменить статус игнорирования пользователя

        Attributes:
            member_id (int): ID пользователя
        
        Returns:
            Объект Response модуля requests
        """

        if member_id == self.current_member.id:
            raise ThisIsYouError(member_id)

        return self.session.post(f"{MAIN_URL}/members/{member_id}/ignore", {'_xfToken': self.token})
    

    def add_profile_message(self, member_id: int, message_html: str) -> Response:
        """Отправить сообщение на стенку пользователя

        Attributes:
            member_id (int): ID пользователя
            message_html (str): Текст сообщения. Рекомендуется использование HTML
            
        Returns:
            Объект Response модуля requests
        """

        return self.session.post(f"{MAIN_URL}/members/{member_id}/post", {'_xfToken': self.token, 'message_html': message_html})
    

    def get_profile_messages(self, member_id: int, page: int = 1) -> list | None:
        """Возвращает ID всех сообщений со стенки пользователя на странице

        Attributes:
            member_id (int): ID пользователя
            page (int): Страница для поиска. По умолчанию 1 (необяз.)
            
        Returns:
            - Cписок (list) с ID всех сообщений профиля
            - None, если пользователя не существует / закрыл профиль
        """

        request = self.session.get(f"{MAIN_URL}/members/{member_id}/page-{page}?_xfResponseType=json&_xfToken={self.token}").json()
        if request['status'] == 'error':
            return None
        
        soup = BeautifulSoup(unescape(request['html']['content']), "lxml")
        return [int(post['id'].strip('js-profilePost-')) for post in soup.find_all('article', {'id': compile('js-profilePost-*')})]


    # POST
    def react_post(self, post_id: int, reaction_id: int = 1) -> Response:
        """Поставить реакцию на сообщение

        Attributes:
            post_id (int): ID сообщения
            reaction_id (int): ID реакции. По умолчанию 1 (необяз.)
            
        Returns:
            Объект Response модуля requests
        """

        return self.session.post(f'{MAIN_URL}/posts/{post_id}/react?reaction_id={reaction_id}', {'_xfToken': self.token})
    

    def edit_post(self, post_id: int, message_html: str) -> Response:
        """Отредактировать сообщение

        Attributes:
            post_id (int): ID сообщения
            message_html (str): Новый текст сообщения. Рекомендуется использование HTML
            
        Returns:
            Объект Response модуля requests
        """

        title_of_thread_post = self.get_post(post_id).thread.title

        return self.session.post(f"{MAIN_URL}/posts/{post_id}/edit", {"title": title_of_thread_post, "message_html": message_html, "message": message_html, "_xfToken": self.token})


    def delete_post(self, post_id: int, reason: str, hard_delete: bool = False) -> Response:
        """Удалить сообщение

        Attributes:
            post_id (int): ID сообщения
            reason (str): Причина для удаления
            hard_delete (bool): Полное удаление сообщения. По умолчанию False (необяз.)
        
        Returns:
            Объект Response модуля requests
        """

        return self.session.post(f"{MAIN_URL}/posts/{post_id}/delete", {"reason": reason, "hard_delete": int(hard_delete), "_xfToken": self.token})
    

    def bookmark_post(self, post_id: int) -> Response:
        """Добавить сообщение в закладки

        Attributes:
            post_id (int): ID сообщения
        
        Returns:
            Объект Response модуля requests
        """

        return self.session.post(f"{MAIN_URL}/posts/{post_id}/bookmark", {"_xfToken": self.token})


    # PROFILE POST
    def react_profile_post(self, post_id: int, reaction_id: int = 1) -> Response:
        """Поставить реакцию на сообщение профиля

        Attributes:
            post_id (int): ID сообщения профиля
            reaction_id (int): ID реакции. По умолчанию 1 (необяз.)
            
        Returns:
            Объект Response модуля requests
        """

        return self.session.post(f'{MAIN_URL}/profile-posts/{post_id}/react?reaction_id={reaction_id}', {'_xfToken': self.token})


    def comment_profile_post(self, post_id: int, message_html: str) -> Response:
        """Прокомментировать сообщение профиля

        Attributes:
            post_id (int): ID сообщения
            message_html (str): Текст комментария. Рекомендуется использование HTML
            
        Returns:
            Объект Response модуля requests
        """

        return self.session.post(f"{MAIN_URL}/profile-posts/{post_id}/add-comment", {"message_html": message_html, "_xfToken": self.token})


    def delete_profile_post(self, post_id: int, reason: str, hard_delete: bool = False) -> Response:
        """Удалить сообщение профиля

        Attributes:
            post_id (int): ID сообщения профиля
            reason (str): Причина для удаления
            hard_delete (bool): Полное удаление сообщения. По умолчанию False (необяз.)
        
        Returns:
            Объект Response модуля requests
        """

        return self.session.post(f"{MAIN_URL}/profile-posts/{post_id}/delete", {"reason": reason, "hard_delete": int(hard_delete), "_xfToken": self.token})
    

    def edit_profile_post(self, post_id: int, message_html: str) -> Response:
        """Отредактировать сообщение профиля
        
        Attributes:
            post_id (int): ID сообщения
            message_html (str): Новый текст сообщения. Рекомендуется использование HTML
            
        Returns:
            Объект Response модуля requests
        """

        return self.session.post(f"{MAIN_URL}/profile-posts/{post_id}/edit", {"message_html": message_html, "message": message_html, "_xfToken": self.token})


    # THREAD
    def answer_thread(self, thread_id: int, message_html: str) -> Response:
        """Оставить сообщение в теме

        Attributes:
            thread_id (int): ID темы
            message_html (str): Текст сообщения. Рекомендуется использование HTML
            
        Returns:
            Объект Response модуля requests
        """

        return self.session.post(f"{MAIN_URL}/threads/{thread_id}/add-reply", {'_xfToken': self.token, 'message_html': message_html})


    def watch_thread(self, thread_id: int, email_subscribe: bool = False, stop: bool = False) -> Response:
        """Изменить статус отслеживания темы

        Attributes:
            thread_id (int): ID темы
            email_subscribe (bool): Отправлять ли уведомления на почту. По умолчанию False (необяз.)
            stop (bool): - Принудительно прекратить отслеживание. По умолчанию False (необяз.)
        
        Returns:
            Объект Response модуля requests
        """

        return self.session.post(f"{MAIN_URL}/threads/{thread_id}/watch", {'_xfToken': self.token, 'stop': int(stop), 'email_subscribe': int(email_subscribe)})
    

    def delete_thread(self, thread_id: int, reason: str, hard_delete: bool = False) -> Response:
        """Удалить тему

        Attributes:
            thread_id (int): ID темы
            reason (str): Причина для удаления
            hard_delete (bool): Полное удаление сообщения. По умолчанию False (необяз.)
            
        Returns:
            Объект Response модуля requests
        """

        return self.session.post(f"{MAIN_URL}/threads/{thread_id}/delete", {"reason": reason, "hard_delete": int(hard_delete), "_xfToken": self.token})
    

    def edit_thread(self, thread_id: int, message_html: str) -> Response:
        """Отредактировать содержимое темы

        Attributes:
            thread_id (int): ID темы
            message_html (str): Новое содержимое ответа. Рекомендуется использование HTML
        
        Returns:
            Объект Response модуля requests
        """

        content = BeautifulSoup(self.session.get(f"{MAIN_URL}/threads/{thread_id}/page-1").content, 'lxml')
        thread_post_id = content.find('article', {'id': compile('js-post-*')})['id'].strip('js-post-')
        return self.session.post(f"{MAIN_URL}/posts/{thread_post_id}/edit", {"message_html": message_html, "message": message_html, "_xfToken": self.token})
    

    def edit_thread_info(self, thread_id: int, title: str, prefix_id: int = None, sticky: bool = True, opened: bool = True) -> Response:
        """Изменить статус темы, ее префикс и название

        Attributes:
            thread_id (int): ID темы
            title (str): Новое название
            prefix_id (int): Новый ID префикса
            sticky (bool): Закрепить (True - закреп / False - не закреп)
            opened (bool): Открыть/закрыть тему (True - открыть / False - закрыть)
        
        Returns:
            Объект Response модуля requests
        """
        
        data = {"_xfToken": self.token, 'title': title}

        if prefix_id is not None: data.update({'prefix_id': prefix_id})
        if opened: data.update({"discussion_open": 1})
        if sticky: data.update({"sticky": 1})

        return self.session.post(f"{MAIN_URL}/threads/{thread_id}/edit", data)
    

    def get_thread_category(self, thread_id: int) -> Category:
        """Получить объект раздела, в котором создана тема

        Attributes:
            thread_id (int): ID темы
        
        Returns:
            Объект Catrgory, в котормо создана тема
        """
        content = BeautifulSoup(self.session.get(f"{MAIN_URL}/threads/{thread_id}/page-1").content, 'lxml')
        
        creator_id = content.find('a', {'class': 'username'})
        if creator_id is None: return None
        
        return self.get_category(int(content.find('html')['data-container-key'].strip('node-')))
    

    def get_thread_posts(self, thread_id: int, page: int = 1) -> list:
        """Получить все сообщения из темы на странице
        
        Attributes:
            thread_id (int): ID темы
            page (int): Cтраница для поиска. По умолчанию 1 (необяз.)
        
        Returns:
            Список (list), состоящий из ID всех сообщений на странице
        """

        request = self.session.get(f"{MAIN_URL}/threads/{thread_id}/page-{page}?_xfResponseType=json&_xfToken={self.token}").json()
        if request['status'] == 'error':
            return None
        
        soup = BeautifulSoup(unescape(request['html']['content']), "lxml")
        return [i['id'].strip('js-post-') for i in soup.find_all('article', {'id': compile('js-post-*')})]
    
    def get_all_thread_posts(self, thread_id: int) -> list:
        """[NEW] Получить все сообщения из темы на всех страницах треда

        Attributes:
            thread_id (int): ID темы

        Returns:
            Список (list), состоящий из ID всех сообщений в теме
        """
        all_posts = []
        page = 1
        while True:
            request = self.session.get(f"{MAIN_URL}/threads/{thread_id}/page-{page}?_xfResponseType=json&_xfToken={self.token}").json()
            if request['status'] == 'error':
                break
            soup = BeautifulSoup(unescape(request['html']['content']), "lxml")
            posts = [i['id'].strip('js-post-') for i in soup.find_all('article', {'id': compile('js-post-*')})]
            if not posts:
                break
            all_posts.extend(posts)
            if page == 1:
                try:
                    pages_count = int(soup.find('ul', {'class': 'pageNav-main'}).find_all('li', {'class': 'pageNav-page'})[-1].text)
                except:
                    pages_count = 1
            if page >= pages_count:
                break
            page += 1
        return all_posts

    def react_thread(self, thread_id: int, reaction_id: int = 1) -> Response:
        """Поставить реакцию на тему

        Attributes:
            thread_id (int): ID темы
            reaction_id (int): ID реакции. По умолчанию 1 (необяз.)
            
        Returns:
            Объект Response модуля requests
        """

        content = BeautifulSoup(self.session.get(f"{MAIN_URL}/threads/{thread_id}/page-1").content, 'lxml')
        thread_post_id = content.find('article', {'id': compile('js-post-*')})['id'].strip('js-post-')
        return self.session.post(f'{MAIN_URL}/posts/{thread_post_id}/react?reaction_id={reaction_id}', {'_xfToken': self.token})


    # OTHER
    def send_form(self, form_id: int, data: dict) -> Response:
        """Заполнить форму

        Attributes:
            form_id (int): ID формы
            data (dict): Информация для запонения в виде словаря. Форма словаря: {'question[id вопроса]' = 'необходимая информация'} | Пример: {'question[531]' = '1'}
        
        Returns:
            Объект Response модуля requests
        """

        data.update({'_xfToken': self.token})
        return self.session.post(f"{MAIN_URL}/form/{form_id}/submit", data)

    def get_notifications(self) -> list:
        """Получить список уведомлений с детальной информацией"""
        content = BeautifulSoup(self.session.get(f"{MAIN_URL}/account/alerts").content, 'lxml')
        notifications = []
        
        for alert in content.find_all('li', {'class': 'js-alert'}):
            if not alert.has_attr('data-alert-id'):
                continue
                
            sender = None
            username_link = alert.find('a', {'class': 'username'})
            if username_link:
                sender = {
                    'id': int(username_link.get('data-user-id', 0)),
                    'name': username_link.get_text(strip=True),
                    'avatar': None,
                    'avatar_color': None,
                    'initials': None
                }
                
                avatar_img = alert.find('img', {'class': 'avatar'})
                avatar_span = alert.find('span', {'class': 'avatar-u'})
                
                if avatar_img and avatar_img.has_attr('src'):
                    sender['avatar'] = avatar_img['src']
                elif avatar_span:
                    sender['avatar_color'] = avatar_span.get('style') 
                    sender['initials'] = avatar_span.get_text(strip=True) if avatar_span else None

            time_tag = alert.find('time')
            timestamp = {
                'iso': time_tag['datetime'] if time_tag else None,
                'unix': int(time_tag['data-time']) if time_tag and time_tag.has_attr('data-time') else None
            } if time_tag else None

            alert_data = {
                'id': alert['data-alert-id'],
                'is_unread': 'is-unread' in alert.get('class', []),
                'text': alert.find('div', {'class': 'contentRow-main'}).get_text(strip=True) if alert.find('div', {'class': 'contentRow-main'}) else None,
                'link': alert.find('a', {'class': 'fauxBlockLink-blockLink'})['href'] if alert.find('a', {'class': 'fauxBlockLink-blockLink'}) else None,
                'sender': sender,
                'timestamp': timestamp
            }
            
            notifications.append(alert_data)
            
        return notifications

    def search_threads(self, query: str, sort: str = 'relevance') -> list:
        """Поиск тем по форуму с заданными параметрами
        
        Attributes:
            query (str): Поисковый запрос
            sort (str): Тип сортировки (relevance, date, etc)
            
        Returns:
            Список словарей с информацией о найденных темах
        """
        url = f"{MAIN_URL}/search/24587779/?q={query}&o={sort}"
        content = BeautifulSoup(self.session.get(url).content, 'lxml')
        results = []
        
        for thread in content.find_all('li', {'class': 'block-row'}):
            title_link = thread.find('h3', {'class': 'contentRow-title'}).find('a')
            date_tag = thread.find('time', {'class': 'u-dt'})
            answers_tag = thread.find(text=compile('Ответы: '))
            
            thread_data = {
                'title': title_link.text.strip().split('| Причина:')[0].strip(),
                'status': thread.find('span', {'class': 'label'}).text if thread.find('span', {'class': 'label'}) else None,
                'author': thread['data-author'],
                'thread_id': int(title_link['href'].split('/')[-2]),
                'create_date': int(date_tag['data-time']) if date_tag else None,
                'answers_count': int(answers_tag.split(': ')[1]) if answers_tag else 0,
                'forum': thread.find('a', href=compile('/forums/')).text if thread.find('a', href=compile('/forums/')) else None,
                'snippet': thread.find('div', {'class': 'contentRow-snippet'}).text.strip() if thread.find('div', {'class': 'contentRow-snippet'}) else None,
                'url': MAIN_URL + title_link['href']
            }
            
            results.append(thread_data)
            
        return results
    
    def mark_notifications_read(self, alert_ids: list[int]) -> Response:
        """Пометить уведомления как прочитанные"""
        data = {
            '_xfToken': self.token,
            'alert_id': alert_ids,
            '_xfAction': 'toggle',
            '_xfWithData': 1
        }
        
        return self.session.post(
            f"{MAIN_URL}/account/alert-toggle",
            data=data
        )
    
    def get_post_bbcode(self, thread_id: int, post_id: int) -> str:
        """Получить BB-код из HTML-содержимого поста
        
        Attributes:
            post_id (int, optional): ID поста для получения HTML-содержимого
            html_content (str, optional): HTML-содержимое поста
            
        Returns:
            str: BB-код поста
        """
        params = {
            '_xfRequestUri': f'/threads/{thread_id}/',
            '_xfWithData': 1,
            '_xfToken': self.token,
            '_xfResponseType': 'json'
        }
            
        response = self.session.get(
            f"{MAIN_URL}/posts/{post_id}/edit",
            params=params
        )
            
        html_content = response.json().get('html', {}).get('content', '')
        
        if not html_content:
            return ''
            
        data = {
            '_xfResponseType': 'json',
            '_xfRequestUri': f'/threads/{thread_id}/',
            '_xfWithData': 1,
            '_xfToken': self.token,
            'html': html_content
        }
        response = self.session.post(
            f"{MAIN_URL}/index.php?editor/to-bb-code",
            data=data
        )
        return response.json().get('bbCode', '')