import logging
import sys

from xbmcgui import DialogProgressBG, ListItem, Dialog
from xbmcplugin import setResolvedUrl

from lib.api.flix.kodi import ADDON_NAME, translate, notification, set_property, get_property
# noinspection PyProtectedMember
from lib.api.flix.provider import get_providers, send_to_providers, ProviderListener, ProviderResult
from lib.dialog_select import dialog_select
from lib.settings import get_providers_timeout, get_resolve_timeout, auto_choose_media, save_last_result
from lib.tmdb import VideoItem, Movie, Show, Season


class ResolveTimeoutError(Exception):
    pass


class NoProvidersError(Exception):
    pass


class ProviderListenerDialog(ProviderListener):
    def __init__(self, providers, method, timeout=10):
        super(ProviderListenerDialog, self).__init__(providers, method, timeout=timeout)
        self._total = len(providers)
        self._count = 0
        self._dialog = DialogProgressBG()

    def on_receive(self, sender):
        self._count += 1
        self._dialog.update(int(100 * self._count / self._total))

    def __enter__(self):
        ret = super(ProviderListenerDialog, self).__enter__()
        self._dialog.create(ADDON_NAME, translate(30111))
        return ret

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            return super(ProviderListenerDialog, self).__exit__(exc_type, exc_val, exc_tb)
        finally:
            self._dialog.close()


def run_providers_method(timeout, method, *args, **kwargs):
    providers = get_providers()
    if not providers:
        raise NoProvidersError("No available providers")
    with ProviderListenerDialog(providers, method, timeout=timeout) as listener:
        send_to_providers(providers, method, *args, **kwargs)
    return listener.data


def run_provider_method(provider, timeout, method, *args, **kwargs):
    with ProviderListener((provider,), method, timeout=timeout) as listener:
        send_to_providers((provider,), method, *args, **kwargs)
    try:
        return listener.data[provider]
    except KeyError:
        raise ResolveTimeoutError("Timeout reached")


def get_providers_results(method, *args, **kwargs):
    results = []
    data = run_providers_method(get_providers_timeout(), method, *args, **kwargs)
    for provider, provider_results in data.items():
        if not isinstance(provider_results, (tuple, list)):
            logging.error("Expecting list or tuple as results for %s:%s", provider, method)
            continue
        for provider_result in provider_results:
            try:
                _provider_result = ProviderResult(provider_result)
            except Exception as e:
                logging.error("Invalid format on provider '%s' result (%s): %s", provider, provider_result, e)
            else:
                if _provider_result.url or _provider_result.provider_data:
                    results.append((provider, _provider_result))
    return results


# Added - sep ":" to "@"
def check_replay(func, sep="@"):
    def wrapper(item, *args, **kwargs):
        if not save_last_result():
            return func(item, *args, **kwargs)

        current_id = str(item)
        key = "flix:last_played:" + item.__class__.__name__ # flix:last_played:EpisodeItem
        value = get_property(key)

        '''
        # Added - important here
        value <<<<<<
        value is concated with : before I changed it to @ to avoid https":" to split together
        elements are split with "@" and subtitles split with "^"
        now you can get subtitles back
        EpisodeItem(id=158300, season=1, episode=1):https://some-site.com/playlist.ext
        '''
        saved_ext_subs = None
        sep_value = value.split(sep)
        if value:
            if len(sep_value) > 2:
                last_id, path, saved_ext_subs = sep_value
            else:
                last_id, path = sep_value
        else:
            last_id = path = saved_ext_subs = None

        # Bookmark - previously played
        # Added - 30147, Previous
        # Don't forget to split it with ^
        if last_id == current_id and Dialog().yesno(ADDON_NAME, translate(30147)):
            setResolvedUrl(int(sys.argv[1]), True, item.to_list_item(path=path, ext_subs=saved_ext_subs.split("^") if saved_ext_subs else None))
        else:
            path = func(item, *args, **kwargs)
            logging.info("path:")
            logging.info(value)
            # Added - alternative way, it looks ugly but works
            '''
            set_property(key, current_id + sep + path)
            TypeError: can only concatenate str to str (not "list, dict whatsoever")
            '''
            if isinstance(path, dict):
                if path['ext_subs']:
                    set_property(key, current_id + sep + path['url'] + sep + "^".join(path['ext_subs']))
                else:
                    set_property(key, current_id + sep + path['url'])
            elif isinstance(path, str):
                set_property(key, current_id + sep + path)
        return path

    return wrapper


@check_replay
def play(item, method, *args, **kwargs):
    try:
        results = get_providers_results(method, *args, **kwargs)
    except NoProvidersError:
        results = None

    path = provider = None
    handle = int(sys.argv[1])

    if results:
        if auto_choose_media():
            selected = 0
        else:
            dialog = dialog_select(translate(30113)) # Result Found
            for p, r in results:
                try:
                    dialog.add_item(label=r.label, label2=r.label2, icon=r.icon)
                except Exception as e:
                    logging.error("Invalid result from provider %s: %s", p, e, exc_info=True)
            dialog.doModal()
            selected = dialog.selected

        if selected >= 0:
            provider, provider_result = results[selected]

            # Bookmark - Provider result URL
            path = provider_result.url
            # Added - Subtitles from providers
            ext_subs = provider_result.ext_subs

            if not path:
                logging.debug("Need to call 'resolve' from provider %s", provider)
                try:
                    path = run_provider_method(
                        provider, get_resolve_timeout(), "resolve", provider_result.provider_data)
                except ResolveTimeoutError:
                    logging.warning("Provider %s took too much time to resolve", provider)
                    notification(translate(30129))
    elif results is None:
        notification(translate(30146))
    else:
        notification(translate(30112))

    # Added - Finally Adding subs to setResolvedUrl
    if path:
        logging.debug("Going to play url '%s' from provider %s", path, provider)
        setResolvedUrl(handle, True, item.to_list_item(path=path, ext_subs=ext_subs if ext_subs else None))
    else:
        setResolvedUrl(handle, False, ListItem())
    return path


def play_search(query):
    play(VideoItem(title=query, art={"icon": "DefaultVideo.png"}), "search", query)


def play_movie(movie_id):
    item = Movie(movie_id)
    play(item, "search_movie", movie_id, item.get_info("originaltitle"), item.alternative_titles,
         year=item.get_info_as("year", int))


def play_show(show_id):
    show = Show(show_id)
    play(show, "search_show", show_id, show.get_info("originaltitle"), show.alternative_titles,
         year=show.get_info_as("year", int))


def play_season(show_id, season_number):
    show = Show(show_id)
    play(Season(show_id, season_number), "search_season", show_id, show.get_info("originaltitle"),
         int(season_number), show.alternative_titles)


def play_episode(show_id, season_number, episode_number):
    show = Show(show_id)
    play(Season(show_id, season_number).get_episode(episode_number), "search_episode", show_id,
         show.get_info("originaltitle"), int(season_number), int(episode_number), show.alternative_titles)
