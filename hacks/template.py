#!/usr/bin/env python
from __future__ import absolute_import, division, with_statement

import datetime
import os
import linecache
import logging

from tornado import escape, gen
from tornado.template import Template, _TemplateReader, _format_code, \
    _Node, _ChunkList, ParseError, _Text, _Expression, _IntermediateControlBlock, \
    _Statement, _IncludeBlock, _Module, _ApplyBlock, _NamedBlock, _ControlBlock, \
    Loader, _ExtendsBlock
from tornado.util import bytes_type, ObjectDict

_DEFAULT_AUTOESCAPE = "xhtml_escape"
_UNSET = object()


class Template(Template):
    """A compiled template.

    We compile into Python from the given template_string. You can generate
    the template from variables with generate().
    """
    def __init__(self, template_string, name="<string>", loader=None,
                 compress_whitespace=None, autoescape=_UNSET):
        self.name = name
        if compress_whitespace is None:
            compress_whitespace = name.endswith(".html") or\
                                  name.endswith(".js")
        if autoescape is not _UNSET:
            self.autoescape = autoescape
        elif loader:
            self.autoescape = loader.autoescape
        else:
            self.autoescape = _DEFAULT_AUTOESCAPE
        self.namespace = loader.namespace if loader else {}
        reader = _TemplateReader(name, escape.native_str(template_string))
        self.file = _File(self, _parse(reader, self))
        self.code = self._generate_python(loader, compress_whitespace)
        self.loader = loader
        try:
            # Under python2.5, the fake filename used here must match
            # the module name used in __name__ below.
            self.compiled = compile(
                escape.to_unicode(self.code),
                "%s.generated.py" % self.name.replace('.', '_'),
                "exec")
        except Exception:
            formatted_code = _format_code(self.code).rstrip()
            logging.error("%s code:\n%s", self.name, formatted_code)
            raise

    def generate(self, **kwargs):
        """Generate this template with the given arguments."""
        namespace = {
            "escape": escape.xhtml_escape,
            "xhtml_escape": escape.xhtml_escape,
            "url_escape": escape.url_escape,
            "json_encode": escape.json_encode,
            "squeeze": escape.squeeze,
            "linkify": escape.linkify,
            "datetime": datetime,
            "_utf8": escape.utf8,  # for internal use
            "_string_types": (unicode, bytes_type),
            # __name__ and __loader__ allow the traceback mechanism to find
            # the generated source code.
            "__name__": self.name.replace('.', '_'),
            "__loader__": ObjectDict(get_source=lambda name: self.code),
        }
        namespace['Task'] = gen.Task
        namespace.update(self.namespace)
        namespace.update(kwargs)

        exec self.compiled in namespace
        execute = namespace["_execute"]
        # Clear the traceback module's cache of source data now that
        # we've generated a new template (mainly for this module's
        # unittests, where different tests reuse the same name).
        linecache.clearcache()
        execute = gen.engine(execute)
        try:
            return execute()
        except Exception:
            formatted_code = _format_code(self.code).rstrip()
            logging.error("%s code:\n%s", self.name, formatted_code)
            raise

class Loader(Loader):
    def _create_template(self, name):
        path = os.path.join(self.root, name)
        f = open(path, "rb")
        template = Template(f.read(), name=name, loader=self)
        f.close()
        return template

class _File(_Node):
    def __init__(self, template, body):
        self.template = template
        self.body = body
        self.line = 0

    def generate(self, writer):
        writer.write_line("def _execute():", self.line)
        with writer.indent():
            writer.write_line("_buffer = []", self.line)
            writer.write_line("_append = _buffer.append", self.line)
            self.body.generate(writer)
            writer.write_line("callback( _utf8('').join(_buffer) )", self.line)

    def each_child(self):
        return (self.body,)


class _AsyncExpression(_Node):
    def __init__(self, expression, line, raw=False):
        self.expression = expression
        self.line = line
        self.raw = raw

    def generate(self, writer):
        writer.write_line("_tmp = yield Task(%s)" % self.expression, self.line)
        writer.write_line("if isinstance(_tmp, _string_types):"
                          " _tmp = _utf8(_tmp)", self.line)
        writer.write_line("else: _tmp = _utf8(str(_tmp))", self.line)
        if not self.raw and writer.current_template.autoescape is not None:
            # In python3 functions like xhtml_escape return unicode,
            # so we have to convert to utf8 again.
            writer.write_line("_tmp = _utf8(%s(_tmp))" %
                              writer.current_template.autoescape, self.line)
        writer.write_line("_append(_tmp)", self.line)


def _parse(reader, template, in_block=None):
    body = _ChunkList([])
    while True:
        # Find next template directive
        curly = 0
        while True:
            curly = reader.find("{", curly)
            if curly == -1 or curly + 1 == reader.remaining():
                # EOF
                if in_block:
                    raise ParseError("Missing {%% end %%} block for %s" %
                                     in_block)
                body.chunks.append(_Text(reader.consume(), reader.line))
                return body
                # If the first curly brace is not the start of a special token,
            # start searching from the character after it
            if reader[curly + 1] not in ("{", "%", "#"):
                curly += 1
                continue
                # When there are more than 2 curlies in a row, use the
            # innermost ones.  This is useful when generating languages
            # like latex where curlies are also meaningful
            if (curly + 2 < reader.remaining() and
                reader[curly + 1] == '{' and reader[curly + 2] == '{'):
                curly += 1
                continue
            break

        # Append any text before the special token
        if curly > 0:
            cons = reader.consume(curly)
            body.chunks.append(_Text(cons, reader.line))

        start_brace = reader.consume(2)
        line = reader.line

        # Template directives may be escaped as "{{!" or "{%!".
        # In this case output the braces and consume the "!".
        # This is especially useful in conjunction with jquery templates,
        # which also use double braces.
        if reader.remaining() and reader[0] == "!":
            reader.consume(1)
            body.chunks.append(_Text(start_brace, line))
            continue

        # Async
        if start_brace == "{{":
            end = reader.find("}}")
            if end == -1:
                raise ParseError("Missing end expression }} on line %d" % line)
            contents = reader.consume(end).strip()
            reader.consume(2)
            if not contents:
                raise ParseError("Empty expression on line %d" % line)
            body.chunks.append(_AsyncExpression(contents, line, True))
            continue

        # Expression
        if start_brace == "{":
            end = reader.find("}")
            if end == -1:
                raise ParseError("Missing end expression } on line %d" % line)
            contents = reader.consume(end).strip()
            reader.consume(2)
            if not contents:
                raise ParseError("Empty expression on line %d" % line)
            body.chunks.append(_Expression(contents, line))
            continue


        # Block
        assert start_brace == "{%", start_brace
        end = reader.find("%}")
        if end == -1:
            raise ParseError("Missing end block %%} on line %d" % line)
        contents = reader.consume(end).strip()
        reader.consume(2)
        if not contents:
            raise ParseError("Empty block tag ({%% %%}) on line %d" % line)

        operator, space, suffix = contents.partition(" ")
        suffix = suffix.strip()

        # Intermediate ("else", "elif", etc) blocks
        intermediate_blocks = {
            "else": set(["if", "for", "while", "try"]),
            "elif": set(["if"]),
            "except": set(["try"]),
            "finally": set(["try"]),
            }
        allowed_parents = intermediate_blocks.get(operator)
        if allowed_parents is not None:
            if not in_block:
                raise ParseError("%s outside %s block" %
                                 (operator, allowed_parents))
            if in_block not in allowed_parents:
                raise ParseError("%s block cannot be attached to %s block" % (operator, in_block))
            body.chunks.append(_IntermediateControlBlock(contents, line))
            continue

        # End tag
        elif operator == "end":
            if not in_block:
                raise ParseError("Extra {%% end %%} block on line %d" % line)
            return body

        elif operator in ("extends", "include", "set", "import", "from",
                          "comment", "autoescape", "raw", "module"):
            if operator == "comment":
                continue
            if operator == "extends":
                suffix = suffix.strip('"').strip("'")
                if not suffix:
                    raise ParseError("extends missing file path on line %d" % line)
                block = _ExtendsBlock(suffix)
            elif operator in ("import", "from"):
                if not suffix:
                    raise ParseError("import missing statement on line %d" % line)
                block = _Statement(contents, line)
            elif operator == "include":
                suffix = suffix.strip('"').strip("'")
                if not suffix:
                    raise ParseError("include missing file path on line %d" % line)
                block = _IncludeBlock(suffix, reader, line)
            elif operator == "set":
                if not suffix:
                    raise ParseError("set missing statement on line %d" % line)
                block = _Statement(suffix, line)
            elif operator == "autoescape":
                fn = suffix.strip()
                if fn == "None":
                    fn = None
                template.autoescape = fn
                continue
            elif operator == "raw":
                block = _Expression(suffix, line, raw=True)
            elif operator == "module":
                block = _Module(suffix, line)
            body.chunks.append(block)
            continue

        elif operator in ("apply", "block", "try", "if", "for", "while"):
            # parse inner body recursively
            block_body = _parse(reader, template, operator)
            if operator == "apply":
                if not suffix:
                    raise ParseError("apply missing method name on line %d" % line)
                block = _ApplyBlock(suffix, line, block_body)
            elif operator == "block":
                if not suffix:
                    raise ParseError("block missing name on line %d" % line)
                block = _NamedBlock(suffix, block_body, template, line)
            else:
                block = _ControlBlock(contents, line, block_body)
            body.chunks.append(block)
            continue

        else:
            raise ParseError("unknown operator: %r" % operator)
