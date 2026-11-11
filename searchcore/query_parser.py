"""Query lexer and recursive-descent parser for boolean and phrase queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from searchcore.tokenizer import tokenize


class QuerySyntaxError(ValueError):
    """Raised when a search query has invalid boolean or phrase syntax."""


@dataclass(frozen=True)
class TermNode:
    """Matches documents containing a single normalized term."""

    term: str


@dataclass(frozen=True)
class PhraseNode:
    """Matches documents containing an exact sequence of adjacent normalized terms."""

    terms: tuple[str, ...]


@dataclass(frozen=True)
class NotNode:
    """Negates a sub-expression (used for boolean exclusion)."""

    operand: QueryNode


@dataclass(frozen=True)
class AndNode:
    """Matches documents satisfying both left and right sub-expressions."""

    left: QueryNode
    right: QueryNode


@dataclass(frozen=True)
class OrNode:
    """Matches documents satisfying either left or right sub-expressions."""

    left: QueryNode
    right: QueryNode


QueryNode = TermNode | PhraseNode | NotNode | AndNode | OrNode


@dataclass(frozen=True)
class _Token:
    kind: Literal["TERM", "PHRASE", "AND", "OR", "NOT", "LPAREN", "RPAREN"]
    value: str


def _lex_query(query: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    n = len(query)

    while i < n:
        ch = query[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "(":
            tokens.append(_Token("LPAREN", "("))
            i += 1
            continue
        if ch == ")":
            tokens.append(_Token("RPAREN", ")"))
            i += 1
            continue
        if ch == '"':
            end = query.find('"', i + 1)
            if end == -1:
                raise QuerySyntaxError("Unclosed quotation mark in query.")
            phrase_raw = query[i + 1 : end]
            tokens.append(_Token("PHRASE", phrase_raw))
            i = end + 1
            continue

        start = i
        while i < n and not query[i].isspace() and query[i] not in '()"':
            i += 1
        word = query[start:i]

        if word == "AND":
            tokens.append(_Token("AND", word))
        elif word == "OR":
            tokens.append(_Token("OR", word))
        elif word == "NOT":
            tokens.append(_Token("NOT", word))
        else:
            tokens.append(_Token("TERM", word))

    return tokens


class _Parser:
    def __init__(
        self,
        tokens: list[_Token],
        default_operator: Literal["AND", "OR"] = "AND",
    ) -> None:
        self.tokens = tokens
        self.pos = 0
        self.default_operator = default_operator

    def peek(self) -> _Token | None:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def consume(self) -> _Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def parse(self) -> QueryNode:
        if not self.tokens:
            raise QuerySyntaxError("Query cannot be empty.")
        node = self._parse_or()
        if self.peek() is not None:
            raise QuerySyntaxError(f"Unexpected token: {self.peek().value!r}")
        return node

    def _parse_or(self) -> QueryNode:
        node = self._parse_and()
        while (tok := self.peek()) is not None and tok.kind == "OR":
            self.consume()
            right = self._parse_and()
            node = OrNode(node, right)
        return node

    def _parse_and(self) -> QueryNode:
        node = self._parse_not()
        while (tok := self.peek()) is not None:
            if tok.kind == "AND":
                self.consume()
                right = self._parse_not()
                node = AndNode(node, right)
            elif tok.kind in ("TERM", "PHRASE", "NOT", "LPAREN"):
                right = self._parse_not()
                if self.default_operator == "OR":
                    node = OrNode(node, right)
                else:
                    node = AndNode(node, right)
            else:
                break
        return node

    def _parse_not(self) -> QueryNode:
        tok = self.peek()
        if tok is not None and tok.kind == "NOT":
            self.consume()
            return NotNode(self._parse_not())
        return self._parse_primary()

    def _parse_primary(self) -> QueryNode:
        tok = self.peek()
        if tok is None:
            raise QuerySyntaxError("Unexpected end of query.")

        if tok.kind == "LPAREN":
            self.consume()
            inner = self._parse_or()
            closing = self.peek()
            if closing is None or closing.kind != "RPAREN":
                raise QuerySyntaxError("Missing closing parenthesis ')'.")
            self.consume()
            return inner

        if tok.kind == "PHRASE":
            self.consume()
            terms = tokenize(tok.value)
            if not terms:
                raise QuerySyntaxError("Phrase query contains no searchable terms.")
            if len(terms) == 1:
                return TermNode(terms[0])
            return PhraseNode(tuple(terms))

        if tok.kind == "TERM":
            self.consume()
            terms = tokenize(tok.value)
            if not terms:
                raise QuerySyntaxError(f"Term {tok.value!r} contains no searchable characters.")
            if len(terms) == 1:
                return TermNode(terms[0])
            # Multi-token unquoted terms like 'e-mail' act as adjacent phrase match.
            return PhraseNode(tuple(terms))

        raise QuerySyntaxError(f"Unexpected token {tok.value!r} where a term or phrase was expected.")


def parse_query(query: str, default_operator: Literal["AND", "OR"] = "AND") -> QueryNode:
    """Parse a search query string into a boolean/phrase AST."""
    if not isinstance(query, str) or not query.strip():
        raise QuerySyntaxError("Query cannot be empty.")
    tokens = _lex_query(query)
    return _Parser(tokens, default_operator=default_operator).parse()


def collect_terms(node: QueryNode) -> set[str]:
    """Return all normalized vocabulary terms referenced in a query AST."""
    if isinstance(node, TermNode):
        return {node.term}
    if isinstance(node, PhraseNode):
        return set(node.terms)
    if isinstance(node, NotNode):
        return collect_terms(node.operand)
    if isinstance(node, (AndNode, OrNode)):
        return collect_terms(node.left) | collect_terms(node.right)
    return set()


def collect_phrases(node: QueryNode) -> set[tuple[str, ...]]:
    """Return all multi-term phrase tuples referenced in a query AST."""
    if isinstance(node, PhraseNode):
        return {node.terms}
    if isinstance(node, NotNode):
        return collect_phrases(node.operand)
    if isinstance(node, (AndNode, OrNode)):
        return collect_phrases(node.left) | collect_phrases(node.right)
    return set()

