import os
import re
from collections import namedtuple

import sublime
import sublime_plugin

from .Functions import camelcase_to_underscore

PLUGIN_NAME = __package__
PLUGIN_DIR = "Packages/%s" % PLUGIN_NAME
PLUGIN_SETTINGS = PLUGIN_NAME + '.sublime-settings'
PLUGIN_CMD = camelcase_to_underscore(PLUGIN_NAME)

settings = None

# {
#     syntaxFile: {
#         'fileName'  : '...',
#         'syntaxName': '...',
#     }
# }
syntaxInfos = {}


def check_any(keywords,string):
    for w in keywords:
        if w in string:
            return True, w

    return False, None


class SpeechType:
    NO_CMD = 0
    TRANSLATE = 1

    translate = namedtuple('translate_cmd', 'replacement, num_chars')
    parse_words = ['parse','horse','parts',"par's",'kars','purse']

    def __init__(self,bindings):
        self.buffer = ''
        self.bindings = bindings

    def add_chars(self,chars):
        self.buffer += chars.lower()

        print('self.buffer')
        print(self.buffer)

    def parse(self,verbose=False):
        if 'clear buffer' in self.buffer:
            self.buffer = ''
            if verbose: print('cleared buffer')
            return self.NO_CMD, None

        cmd=self.buffer
        match, word = check_any(self.parse_words,cmd)
        if match:
            b = cmd.replace(word,'')

            if 'letters' in cmd:
                if verbose: print('replace: '+cmd)
                
                b = b.replace(' ','')
                b = b.replace('letters','')
                
                if len(b) < 1:
                    return self.NO_CMD, None
                
                for key in self.bindings['letters'].keys():
                    b = b.replace(key,self.bindings['letters'][key])

                if verbose: print('with: '+b)

                self.buffer = ''
                return self.TRANSLATE, self.translate(replacement=b,num_chars=len(cmd))

            else:
                self.buffer = ''
                if verbose: print("couldn't parse: "+b)
                if verbose: print('cleared buffer')
                return self.NO_CMD, None 

        return self.NO_CMD, None





def plugin_loaded():
    global settings

    settings = sublime.load_settings(PLUGIN_SETTINGS)


class SpeechTypeSublimeCommand(sublime_plugin.TextCommand):
    global settings

    def run(self, edit, regions=[], replacement=''):
        v = sublime.active_window().active_view()

        cursorPlaceholder = settings.get('cursor_placeholder', None)
        cursorFixedOffset = 0

        # validate the format of `replacement`
        if isinstance(cursorPlaceholder, str):
            cursorPlaceholderCount = replacement.count(cursorPlaceholder)

            # wrong usage
            if cursorPlaceholderCount > 1:
                print('[{}] ERROR: More than one cursor placeholder in `{}`'.format(PLUGIN_NAME, replacement))
                return False

            # correct usage
            if cursorPlaceholderCount == 1:
                cursorFixedOffset = replacement.index(cursorPlaceholder) + len(cursorPlaceholder) - len(replacement)
                replacement = replacement.replace(cursorPlaceholder, '', 1)

        # regions need to be replaced in a reversed sorted order
        for region in self.reverse_sort_regions(regions):
            v.replace(
                edit,
                sublime.Region(region[0], region[1]),
                replacement
            )

            # correct cursor positions
            if cursorFixedOffset < 0:
                sels = v.sel()
                # remove the old cursor
                cursorPosition = region[0] + len(replacement)
                sels.subtract(sublime.Region(
                    cursorPosition,
                    cursorPosition
                ))
                # add a new cursor
                cursorPositionFixed = cursorPosition + cursorFixedOffset
                sels.add(sublime.Region(
                    cursorPositionFixed,
                    cursorPositionFixed
                ))

        return True

    def reverse_sort_regions(self, regions):
        """
        sort `regions` in a descending order

        @param      self     The object
        @param      regions  A list of region which is in tuple form

        @return     `regions` in a descending order.
        """

        return sorted(regions, key=lambda region: region[0], reverse=True)


class SpeechTypeSublimeListener(sublime_plugin.EventListener):
    global settings, syntaxInfos

    def __init__(self):
        self.sourceScopeRegex = re.compile(r'\b(?:source|text)\.[^\s]+')
        self.nameXmlRegex = re.compile(r'<key>name</key>\s*<string>(.*?)</string>', re.DOTALL)
        self.nameYamlRegex = re.compile(r'^name\s*:(.*)$', re.MULTILINE)
        
        settings2 = sublime.load_settings(PLUGIN_SETTINGS)
        # print('yo1') 
        # print(settings.get('bindings','s'))
        self.speech_type = SpeechType(settings2.get('bindings',[])[1])
        # self.speech_type = SpeechType([])
       
        print('yo2')

    def on_modified(self, view):
        """
        called after changes have been made to a view

        @param      self  The object
        @param      view  The view

        @return     True if a replacement happened, False otherwise.
        """

        v = sublime.active_window().active_view()

        # fix the issue that breaks functionality for undo/soft_undo
        historyCmd = v.command_history(1)  # this is from the redo stack
        if historyCmd[0] == PLUGIN_CMD:
            return False

        # print(v.command_history(0))
        # print(v.change_count())

        # no action if we are not typing
        historyCmd = v.command_history(0)
        if historyCmd[0] != 'insert':
            return False
        # get the last inserted chars
        lastInsertedChars = historyCmd[1]['characters']

        # on_modified gets called for every single character addition, so we should only grab the last character to be added. 
        if len(lastInsertedChars) > 0:
            self.speech_type.add_chars(lastInsertedChars[-1])

        # collect scopes from the selection
        # we expect the fact that most regions would have the same scope
        scopesInSelection = {
            v.scope_name(region.begin()).rstrip()
            for region in v.sel()
        }

        # generate valid source scopes
        sourceScopes = (
            set(self.get_current_syntax(v)) |
            set(self.sourceScopeRegex.findall(' '.join(scopesInSelection)))
        )

        # try possible working bindings
        for binding in settings.get('bindings', []):

            if sourceScopes & set(binding['syntax_list']):

                cmd, args = self.speech_type.parse(verbose=True)

                if cmd:
                    if cmd == SpeechType.TRANSLATE:
                        self.do_replace(v, args.replacement, args.num_chars)

                # success = self.do_replace_old(v, binding, lastInsertedChars)
                
                
                # print(binding)
                # print(sourceScopes)
                # print(success)
                # from datetime import datetime
                # print(datetime.utcnow())

        return True

    def get_current_syntax(self, view):
        """
        get the syntax file name and the syntax name which is on the
        bottom-right corner of ST

        @param      self  The object
        @param      view  The view

        @return     The current syntax.
        """

        syntaxFile = view.settings().get('syntax')

        if syntaxFile not in syntaxInfos:
            syntaxInfos[syntaxFile] = {
                'fileName' : os.path.splitext(os.path.basename(syntaxFile))[0],
                'syntaxName' : self.find_syntax_name(syntaxFile),
            }

        return [
            v
            for v in syntaxInfos[syntaxFile].values()
            if isinstance(v, str)
        ]

    def find_syntax_name(self, syntaxFile):
        """
        find the name section in the give syntax file path

        @param      self        The object
        @param      syntaxFile  The path of a syntax file

        @return     The syntax name of `syntaxFile` or None.
        """

        content = sublime.load_resource(syntaxFile).strip()

        # .tmLanguage (XML)
        if content.startswith('<'):
            matches = self.nameXmlRegex.search(content)
        # .sublime-syntax (YAML)
        else:
            matches = self.nameYamlRegex.search(content)

        if matches is None:
            return None

        return matches.group(1).strip()

    def do_replace_old(self, view, binding, lastInsertedChars):
        """
        try to do replacement with given a binding and last inserted chars

        @param      self               The object
        @param      view               The view object
        @param      binding            A binding in `bindings` in the settings
                                       file
        @param      lastInsertedChars  The last inserted characters

        @return     True/False on success/failure.
        """

        for search, replacement in binding['keymaps'].items():
            # skip a keymap as early as possible
            if not (
                search.endswith(lastInsertedChars) or
                lastInsertedChars.endswith(search)
            ):
                continue

            regionsToBeReplaced = []

            # iterate each region
            # view.sel() returns all the regions for the carets (selections) that currently exist in the file, so you can do replacement at multiple carets
            for region in view.sel():
                # print('regions')
                # print(region.begin())
                # print(region.end())
                checkRegion = sublime.Region(
                    region.begin() - len(search),
                    region.end()
                )
                # print('substr(checkRegion)')
                # print(view.substr(checkRegion))
                if view.substr(checkRegion) == search:
                    regionsToBeReplaced.append((
                        checkRegion.begin(),
                        checkRegion.end()
                    ))

            if regionsToBeReplaced:
                return view.run_command(PLUGIN_CMD, {
                    'regions'     : regionsToBeReplaced,
                    'replacement' : replacement,
                })

        return False

    def do_replace(self, view, replacement, num_chars_to_replace):

        regionsToBeReplaced = []

        # iterate over each selected region
        # view.sel() returns all the regions for the carets (selections) that currently exist in the file, so you can do replacement at multiple carets
        for region in view.sel():
            # print('regions')
            # print(region.begin())
            # print(region.end())
            checkRegion = sublime.Region(
                region.begin() - num_chars_to_replace,
                region.end()
            )

            regionsToBeReplaced.append((
                    checkRegion.begin(),
                    checkRegion.end()
                ))
            # print('substr(checkRegion)')
            # print(view.substr(checkRegion))
            # if view.substr(checkRegion) == search:
            #     regionsToBeReplaced.append((
            #         checkRegion.begin(),
            #         checkRegion.end()
            #     ))

        if regionsToBeReplaced:
            return view.run_command(PLUGIN_CMD, {
                'regions'     : regionsToBeReplaced,
                'replacement' : replacement,
            })