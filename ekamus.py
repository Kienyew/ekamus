#!/usr/bin/env python3
# modified at 2018年10月07日12:14:09
# modified at 2019-12-03 13:45
from __future__ import annotations

import re
import os
import sys
import json
import sqlite3
import argparse
import itertools
from termcolor import colored
from typing import Union, List, Tuple, Optional


class EKamus:
    DATABASE_PATH = os.path.dirname(
        os.path.realpath(__file__)) + '/kamus.sqlite3'

    def __init__(self, self_feedback=True):
        if not os.path.exists(EKamus.DATABASE_PATH):
            EKamus.create_database()

        self.database = sqlite3.connect(EKamus.DATABASE_PATH)
        self.self_feedback = self_feedback

    @classmethod
    def create_database(cls):
        if os.path.exists(cls.DATABASE_PATH):
            os.rename(cls.DATABASE_PATH, cls.DATABASE_PATH + '.bak')

        database = sqlite3.connect(cls.DATABASE_PATH)
        cursor = database.cursor()

        create_statement = 'CREATE TABLE kamus (word VARCHAR NOT NULL, def VARCHAR NOT NULL, PRIMARY KEY(word))'
        cursor.execute(create_statement)

        create_statement = 'CREATE TABLE chinese_to_malay (chinese_word VARCHAR NOT NULL, list_json VARCHAR NOT NULL, PRIMARY KEY(chinese_word))'
        cursor.execute(create_statement)

        database.commit()
        database.close()

    def __del__(self):
        if self.self_feedback:
            self.database.commit()

        self.database.close()

    def search_local(self, word: str) -> EKamusResult:
        query_results = self.database.cursor().execute(
            'SELECT def FROM kamus WHERE word = (?)', (word,)).fetchall()
        if len(query_results) == 0:
            return None

        return EKamusResult.fromJson(query_results[0][0])

    def search_online(self, word: str) -> Union[EKamusResult, None]:
        import requests
        import bs4

        def search_exact_match(word: str) -> Union[EKamusResult, None]:
            url = 'http://www.ekamus.info/index.php/term/马来文-华文字典,{}.xhtml'.format(
                word)
            res = requests.get(url, timeout=10)
            soup = bs4.BeautifulSoup(res.content, 'lxml')
            term_tag = soup.select_one(
                '.lead.text-primary.font-weight-bold')
            term = '?' if term_tag is None else term_tag.text.strip()
            if term == '?':
                return None

            defn = soup.select_one('.defn')
            word_definitions = []
            for i in defn.children:
                if isinstance(i, bs4.NavigableString):
                    word_definitions.append(i)
                elif isinstance(i, bs4.Tag):
                    if i.name == 'p':
                        break

            variations = {}
            for p in defn.find_all('p'):
                title_tag = p.find('strong')
                title = title_tag.text.strip()
                variations[title] = []
                for i in title_tag.next_siblings:
                    if isinstance(i, bs4.NavigableString):
                        variations[title].append(i.strip())
                    if i.parent != p:
                        break

            result = EKamusResult(term, variations, word_definitions)
            if self.self_feedback:
                self.insert_to_database(result)

            return result

        if result := search_exact_match(word):
            return result

        # Try to get the root word from web if fail.
        try_url = 'http://www.ekamus.info/index.php?a=srch&srch%5Badv%5D=all&srch%5Bby%5D=d&srch%5Bin%5D=-1&d=1&q={}&search=查询'.format(
            word)
        try_res = requests.get(try_url)
        try_soup = bs4.BeautifulSoup(try_res.content, 'lxml')
        search_tag_match_a = next(filter(lambda a: a['href'].startswith(
            '/index.php/term/'), try_soup.select('a[href]')), None)
        if search_tag_match_a is None:
            return None
        else:
            return search_exact_match(search_tag_match_a.text)

    def search_chinese_online(self, chinese_word: str) -> List[EKamusResult]:
        import requests
        import bs4

        url = f'https://www.ekamus.info/index.php?q={chinese_word}&search=查询&srch[adv]=all&srch[by]=d&srch[in]=-1&a=srch&d=1'
        html = requests.get(url).text
        soup = bs4.BeautifulSoup(html, 'lxml')
        results = []
        for tag in soup.select('div.card-title\\" > dt > a[href]'):
            malay_word = tag.text.strip()
            results += [self.search(malay_word)]

        if self.self_feedback:
            execute_statement = 'INSERT OR IGNORE INTO chinese_to_malay (chinese_word, list_json) VALUES(?, ?)'
            list_json = json.dumps([result.word for result in results])
            self.database.cursor().execute(execute_statement, (chinese_word, list_json))

        return results

    def search_chinese_local(self, chinese_word: str) -> Optional[List[EKamusResult]]:
        execute_statement = 'SELECT list_json FROM chinese_to_malay WHERE chinese_word = (?)'
        results = self.database.cursor().execute(
            execute_statement, [chinese_word]).fetchone()

        if results is None:
            return None

        list_json = results[0]
        malay_words = json.loads(list_json)

        return [*map(self.search, malay_words)]

    def search_chinese(self, chinese_word) -> Optional[List[EKamusResult]]:
        return self.search_chinese_local(chinese_word) or self.search_chinese_online(chinese_word)

    def search(self, word: str) -> EKamusResult:
        return self.search_local(word) or self.search_online(word)

    def insert_to_database(self, result: EKamusResult):
        result_json = result.toJson()
        for variations in itertools.chain(result.variations, [result.word]):
            execute_statement = 'INSERT OR IGNORE INTO kamus (word, def) VALUES (?, ?)'
            self.database.cursor().execute(execute_statement, (variations, result_json))


class EKamusResult:
    global json

    def __init__(self, word: str, variations: dict = None, definitions: list = None):
        self.word = word
        self.definitions = definitions
        self.variations = variations

    def __repr__(self) -> str:
        return f'{type(self).__name__}({self.word})'

    def generateOutput(self) -> str:
        output = '\t' + colored(self.word, 'cyan',
                                attrs=['bold', 'underline']) + '\n'

        for i in self.definitions:
            output += colored(i, 'white', attrs=['bold']) + '\n'

        output += '\n'

        for i, k in enumerate(self.variations):
            v = self.variations[k]
            output += '{}. {}\n'.format(colored(i + 1, 'white'),
                                        colored(k, 'yellow', attrs=['bold']))
            for d in v:
                output += ('\t' + d + '\n')
            output += '\n'

        return output

    def toJson(self) -> str:
        return json.dumps({
            'word': self.word,
            'definitions': self.definitions,
            'variations': self.variations
        })

    @staticmethod
    def fromJson(json_string: str):
        tmp = json.loads(json_string)
        return EKamusResult(tmp['word'], tmp['variations'], tmp['definitions'])


def parse_args() -> Tuple[argparse.ArgumentParser, argparse.Namespace]:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument(
        'word', nargs='*', metavar='word', help='word to search')

    args = argument_parser.parse_args()
    return argument_parser, args


def main():
    argument_parser, args = parse_args()
    word = ' '.join(args.word)
    ekamus = EKamus(self_feedback=True)

    # contains chinese character
    if re.match('[\u4e00-\u9fff]+', word):
        results = ekamus.search_chinese(word)
        print(colored(word, color='white', attrs=['bold']), end='\n\n')
        for i, result in enumerate(results, 1):
            output = '{index:2}: {word}\n\t{definitions}'.format(
                index=colored(i, 'yellow', attrs=['bold']),
                word=colored(result.word, 'cyan', attrs=['underline', 'bold']),
                definitions='\n\t'.join(result.definitions)
            )

            print(output, end='\n\n')

    else:
        if word != '':
            result = ekamus.search(word)
            if result is not None:
                print(result.generateOutput())
            else:
                sys.stderr.write(f"can't find: {word}\n")

        else:
            argument_parser.print_help()
            sys.exit(1)


if __name__ == '__main__':
    main()
