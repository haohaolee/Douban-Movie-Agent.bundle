import time

API_BASE_URL = "https://api.douban.com/v2/movie/"
DOUBAN_MOVIE_SEARCH = API_BASE_URL + 'search?q=%s'
DOUBAN_MOVIE_SUBJECT = API_BASE_URL + 'subject/%s/'
DOUBAN_MOVIE_IMDB_QUERY = API_BASE_URL + 'imdb/%s/'
DOUBAN_MOVIE_BASE = 'http://movie.douban.com/subject/%s/'
REQUEST_RETRY_LIMIT = 3

RE_IMDB_ID = Regex('^tt\d+$')
RE_DOUBAN_ID = Regex('\d+$')

################################################################################################


def Start():
    HTTP.CacheTime = CACHE_1WEEK

################################################################################################

class DBMAgent(Agent.Movies):
    name = 'Douban Movie Database'
    languages = [Locale.Language.English, Locale.Language.Chinese]

    primary_provider = True
    accepts_from = ['com.plexapp.agents.localmedia']
    contributes_to = ['com.plexapp.agents.imdb']

    def search(self, results, media, lang, manual):

        # If search is initiated by a different, primary metadata agent.
        # This requires the other agent to use the IMDb id as key.
        if media.primary_metadata is not None and RE_IMDB_ID.search(media.primary_metadata.id):
            results.Append(MetadataSearchResult(
                id = media.primary_metadata.id,
                score = 100
            ))
            return

        # manual search and name is IMDB id
        if manual and RE_IMDB_ID.search(media.name):
            search_url = DOUBAN_MOVIE_IMDB_QUERY % media.name

            dbm_dict = self.get_json(url=search_url)
            if dbm_dict:
                results.Append(MetadataSearchResult(
                    id = media.name,
                    name = dbm_dict['title'],
                    year = dbm_dict['year'][0],
                    lang = lang
                    ))
            return

        # automatic search
        search_url = DOUBAN_MOVIE_SEARCH % media.name
        dbm_dict = self.get_json(url=search_url)
        if dbm_dict and 'subjects' in dbm_dict:

            for i, movie in enumerate(dbm_dict['subjects']):

                # if it's episode, then continue
                if movie['subtype'] != 'movie':
                    continue

                score = 90

                dist = abs(String.LevenshteinDistance(
                                movie['title'].lower(),
                                media.name.lower())
                            )

                if movie['original_title'] != movie['title']:
                    dist = min(abs(String.LevenshteinDistance(
                                        movie['original_title'].lower(),
                                        media.name.lower())),
                                dist)

                score = score - dist

                # Adjust score slightly for 'popularity' (helpful for similar or identical titles when no media.year is present)
                score = score - (5 * i)

                release_year = None
                if 'year' in movie and movie['year'] != '':
                    try:
                        release_year = int(movie['year'])
                    except:
                        pass

                if media.year and int(media.year) > 1900 and release_year:
                    year_diff = abs(int(media.year) - release_year)
                    if year_diff <= 1:
                        score = score + 10
                    else:
                        score = score - (5 * year_diff)

                if score <= 0:
                    continue
                else:
                    imdb_id = self.get_imdb(movie['id'])
                    if imdb_id:
                        results.Append(MetadataSearchResult(
                            id = imdb_id,
                            name = movie['title'],
                            year = release_year,
                            score = score,
                            lang = lang
                        ))


    def update(self, metadata, media, lang):

        proxy = Proxy.Preview

        dbm_imdb = self.get_json(url=DOUBAN_MOVIE_IMDB_QUERY % metadata.id)

        # Try to get douban id
        if not dbm_imdb or not dbm_imdb['id']:
            return
        m = RE_DOUBAN_ID.search(dbm_imdb['id'])
        if not m:
            Log('Cannot find douban id from imdb query')
            return
        dbm_dict = self.get_json(url=DOUBAN_MOVIE_SUBJECT % m.group(0))
        if not dbm_dict:
            return

        # Rating
        votes = dbm_dict['ratings_count']
        rating =  dbm_dict['rating']['average']
        if votes > 3:
            metadata.rating = float(rating)

        # Title of the film
        metadata.title = dbm_dict['title']

        if metadata.title != dbm_dict['original_title']:
            metadata.original_title = dbm_dict['original_title']

        # Summary
        if dbm_dict['summary']:
            metadata.summary = dbm_dict['summary']

        # Genres
        metadata.genres.clear()
        for genre in dbm_dict['genres']:
            metadata.genres.add(genre.strip())

        # Tagline
        metadata.tagline = ' '.join([ i['name'] for i in dbm_imdb['tags'] ])

        # Directors
        metadata.directors.clear()
        for member in dbm_imdb['attrs']['director']:
            metadata.directors.add(member)

        # Writers
        metadata.writers.clear()
        for member in dbm_imdb['attrs']['writer']:
            metadata.writers.add(member)

        # Casts
        metadata.roles.clear()
        for member in dbm_imdb['attrs']['cast']:
            role = metadata.roles.new()
            role.actor = member

        if len(metadata.posters.keys()) == 0:

            poster_url = dbm_dict['images']['large']
            thumb_url = dbm_dict['images']['small']
            metadata.posters[poster_url] = proxy(HTTP.Request(thumb_url), sort_order=1)

    def get_imdb(self, db_id):
        url = DOUBAN_MOVIE_BASE % db_id
        for t in reversed(range(REQUEST_RETRY_LIMIT)):
            try:
                result = HTML.ElementFromURL(url)
            except:
                Log('Error fetching HTML from Douban Site, will try %s more time(s) before giving up.', str(t))
                time.sleep(5)
                continue
            else:
                break

        if not result:
            return None

        for el in result.xpath('//div[@id="info"]/a[@rel="nofollow"]/text()'):
            m = RE_IMDB_ID.search(el)
            if m:
                return m.group(0)

        return None


    def get_json(self, url, cache_time=CACHE_1HOUR * 3):
    # try n times waiting 5 seconds in between if something goes wrong
        result = None
        for t in reversed(range(REQUEST_RETRY_LIMIT)):
            try:
                result = JSON.ObjectFromURL(url, sleep=2.0, cacheTime=cache_time)
            except:
                Log('Error fetching JSON from The Movie Database, will try %s more time(s) before giving up.', str(t))
                time.sleep(5)
                continue

            if isinstance(result, dict):
                return result

        Log('Error fetching JSON from The Movie Database.')
        return None


