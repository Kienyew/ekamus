#!/usr/bin/env python3
# modified at 2018年10月07日12:14:09
# modified at 2019-12-03 13:45
from __future__ import annotations

import os
import sys
import sqlite3
import argparse
import itertools
from termcolor import colored
from typing import Union, Tuple


class EKamus:
    DATABASE_PATH = os.path.dirname(os.path.realpath(__file__)) + '/kamus.sqlite3'

    def __init__(self, self_feedback=True):
        if not os.path.exists(EKamus.DATABASE_PATH):
            self.create_database()

        self.database = sqlite3.connect(EKamus.DATABASE_PATH)
        self.self_feedback = self_feedback

    def create_database(self):
        create_statement = 'CREATE TABLE kamus (word VARCHAR NOT NULL, def VARCHAR NOT NULL, PRIMARY KEY(word))'
        if os.path.exists(EKamus.DATABASE_PATH):
            os.rename(EKamus.DATABASE_PATH, EKamus.DATABASE_PATH + '.bak')

        database = sqlite3.connect(EKamus.DATABASE_PATH)
        cursor = database.cursor()
        cursor.execute(create_statement)
        database.commit()
        database.close()

    def __del__(self):
        if self.self_feedback:
            self.database.commit()

        self.database.close()

    def search_local(self, word: str) -> EKamusResult:
        query_results = self.database.cursor().execute('SELECT def FROM kamus WHERE word = (?)', (word,)).fetchall()
        if len(query_results) == 0:
            return None

        return EKamusResult.fromJson(query_results[0][0])

    def search_online(self, word: str) -> Union[EKamusResult, None]:
        import requests
        import bs4
        def search_exact_match(word: str) -> Union[EKamusResult, None]:
            try:
                url = 'http://www.ekamus.info/index.php/term/马来文-华文字典,{}.xhtml'.format(word)
                res = requests.get(url, timeout=10)
                soup = bs4.BeautifulSoup(res.content, 'lxml')
                term_tag = soup.select_one('.lead.text-primary.font-weight-bold')
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

                variation = {}
                for p in defn.find_all('p'):
                    title_tag = p.find('strong')
                    title = title_tag.text.strip()
                    variation[title] = []
                    for i in title_tag.next_siblings:
                        if isinstance(i, bs4.NavigableString):
                            variation[title].append(i.strip())
                        if i.parent != p:
                            break

                result = EKamusResult(term, variation, word_definitions)
                if self.self_feedback:
                    self.insert_to_database(result)

                return result

            except:
                raise

        if result := search_exact_match(word):
            return result

        # Try to get the root word from web if fail.
        try_url = 'http://www.ekamus.info/index.php?a=srch&srch%5Badv%5D=all&srch%5Bby%5D=d&srch%5Bin%5D=-1&d=1&q={}&search=查询'.format(word)
        try_res = requests.get(try_url)
        try_soup = bs4.BeautifulSoup(try_res.content, 'lxml')
        search_tag_match_a = next(filter(lambda a: a['href'].startswith('/index.php/term/'), try_soup.select('a[href]')), None)
        if search_tag_match_a is None:
            return None
        else:
            return search_exact_match(search_tag_match_a.text)

    def search(self, word: str) -> EKamusResult:
        return self.search_local(word) or self.search_online(word)

    def insert_to_database(self, result: EKamusResult):
        result_json = result.toJson()
        for variation in itertools.chain(result.variation, [result.word]):
            self.database.cursor().execute('INSERT INTO kamus (word, def) VALUES (?, ?)', (variation, result_json))

    def definition_includes(self, fragment: str) -> list:
        res_words = self.database.cursor() \
            .execute('SELECT word FROM kamus WHERE lower(def) LIKE (?)', (f'%{fragment.lower()}%',)) \
            .fetchall()

        return [word[0] for word in res_words]

class EKamusResult:
    global json

    def __init__(self, word: str, variation: dict=None, definitions: list=None):
        self.word = word
        self.definitions = definitions
        self.variation = variation

    def __repr__(self) -> str:
        return f'{type(self).__name__}({self.word})'

    def generateOutput(self) -> str:
        output = '\t' + colored(self.word, 'cyan',
                                attrs=['bold', 'underline']) + '\n'

        for i in self.definitions:
            output += colored(i, 'white', attrs=['bold']) + '\n'

        output += '\n'

        for i, k in enumerate(self.variation):
            v = self.variation[k]
            output += '{}. {}\n'.format(colored(i + 1, 'white'),
                                        colored(k, 'yellow', attrs=['bold']))
            for d in v:
                output += ('\t' + d + '\n')
            output += '\n'

        return output

    def toJson(self) -> str:
        import json
        return json.dumps({
            'word': self.word,
            'definitions': self.definitions,
            'variation': self.variation
        })

    @staticmethod
    def fromJson(json_string: str):
        import json
        tmp = json.loads(json_string)
        return EKamusResult(tmp['word'], tmp['variation'], tmp['definitions'])


def parse_args() -> Tuple[argparse.ArgumentParser, argparse.Namespace]:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument('word', nargs='*', metavar='word', help='word to search')
    argument_parser.add_argument('--include-word', nargs='?', metavar='WORD', type=str, help='search for words where the definition includes WORD')
    args = argument_parser.parse_args()
    return (argument_parser, args)

def main():
    argument_parser, args = parse_args()
    if args.include_word:
        for word in EKamus().definition_includes(args.include_word):
            print(word)

        sys.exit(0)

    word = ' '.join(args.word)
    if word != '':
        ekamus = EKamus(self_feedback=True)
        result = ekamus.search(word)
        if result is not None:
            print(result.generateOutput())
            sys.exit(0)
        else:
            sys.stderr.write(f"can't find: {word}\n")
            sys.exit(1)

    else:
        argument_parser.print_help()
        sys.exit(1)

if __name__ == '__main__':
    main()
