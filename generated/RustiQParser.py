# Generated from RustiQ.g4 by ANTLR 4.13.2
# encoding: utf-8
from antlr4 import *
from io import StringIO
import sys
if sys.version_info[1] > 5:
	from typing import TextIO
else:
	from typing.io import TextIO

def serializedATN():
    return [
        4,1,15,50,2,0,7,0,2,1,7,1,2,2,7,2,2,3,7,3,2,4,7,4,1,0,5,0,12,8,0,
        10,0,12,0,15,9,0,1,0,1,0,1,1,1,1,1,1,1,1,1,1,1,1,3,1,25,8,1,1,1,
        1,1,1,2,1,2,5,2,31,8,2,10,2,12,2,34,9,2,1,2,1,2,1,3,1,3,1,3,1,3,
        1,4,1,4,1,4,5,4,45,8,4,10,4,12,4,48,9,4,1,4,0,0,5,0,2,4,6,8,0,0,
        48,0,13,1,0,0,0,2,18,1,0,0,0,4,28,1,0,0,0,6,37,1,0,0,0,8,41,1,0,
        0,0,10,12,3,2,1,0,11,10,1,0,0,0,12,15,1,0,0,0,13,11,1,0,0,0,13,14,
        1,0,0,0,14,16,1,0,0,0,15,13,1,0,0,0,16,17,5,0,0,1,17,1,1,0,0,0,18,
        19,5,1,0,0,19,20,5,11,0,0,20,21,5,4,0,0,21,24,5,5,0,0,22,23,5,8,
        0,0,23,25,5,3,0,0,24,22,1,0,0,0,24,25,1,0,0,0,25,26,1,0,0,0,26,27,
        3,4,2,0,27,3,1,0,0,0,28,32,5,6,0,0,29,31,3,6,3,0,30,29,1,0,0,0,31,
        34,1,0,0,0,32,30,1,0,0,0,32,33,1,0,0,0,33,35,1,0,0,0,34,32,1,0,0,
        0,35,36,5,7,0,0,36,5,1,0,0,0,37,38,5,2,0,0,38,39,3,8,4,0,39,40,5,
        9,0,0,40,7,1,0,0,0,41,46,5,12,0,0,42,43,5,10,0,0,43,45,5,12,0,0,
        44,42,1,0,0,0,45,48,1,0,0,0,46,44,1,0,0,0,46,47,1,0,0,0,47,9,1,0,
        0,0,48,46,1,0,0,0,4,13,24,32,46
    ]

class RustiQParser ( Parser ):

    grammarFileName = "RustiQ.g4"

    atn = ATNDeserializer().deserialize(serializedATN())

    decisionsToDFA = [ DFA(ds, i) for i, ds in enumerate(atn.decisionToState) ]

    sharedContextCache = PredictionContextCache()

    literalNames = [ "<INVALID>", "'fn'", "'return'", "'i32'", "'('", "')'", 
                     "'{'", "'}'", "'->'", "';'", "'+'" ]

    symbolicNames = [ "<INVALID>", "FN", "RETURN", "I32", "LPAREN", "RPAREN", 
                      "LBRACE", "RBRACE", "ARROW", "SEMICOLON", "PLUS", 
                      "IDENT", "INT", "LINE_COMMENT", "BLOCK_COMMENT", "WS" ]

    RULE_program = 0
    RULE_functionDecl = 1
    RULE_block = 2
    RULE_statement = 3
    RULE_expression = 4

    ruleNames =  [ "program", "functionDecl", "block", "statement", "expression" ]

    EOF = Token.EOF
    FN=1
    RETURN=2
    I32=3
    LPAREN=4
    RPAREN=5
    LBRACE=6
    RBRACE=7
    ARROW=8
    SEMICOLON=9
    PLUS=10
    IDENT=11
    INT=12
    LINE_COMMENT=13
    BLOCK_COMMENT=14
    WS=15

    def __init__(self, input:TokenStream, output:TextIO = sys.stdout):
        super().__init__(input, output)
        self.checkVersion("4.13.2")
        self._interp = ParserATNSimulator(self, self.atn, self.decisionsToDFA, self.sharedContextCache)
        self._predicates = None




    class ProgramContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def EOF(self):
            return self.getToken(RustiQParser.EOF, 0)

        def functionDecl(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(RustiQParser.FunctionDeclContext)
            else:
                return self.getTypedRuleContext(RustiQParser.FunctionDeclContext,i)


        def getRuleIndex(self):
            return RustiQParser.RULE_program

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitProgram" ):
                return visitor.visitProgram(self)
            else:
                return visitor.visitChildren(self)




    def program(self):

        localctx = RustiQParser.ProgramContext(self, self._ctx, self.state)
        self.enterRule(localctx, 0, self.RULE_program)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 13
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            while _la==1:
                self.state = 10
                self.functionDecl()
                self.state = 15
                self._errHandler.sync(self)
                _la = self._input.LA(1)

            self.state = 16
            self.match(RustiQParser.EOF)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class FunctionDeclContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def FN(self):
            return self.getToken(RustiQParser.FN, 0)

        def IDENT(self):
            return self.getToken(RustiQParser.IDENT, 0)

        def LPAREN(self):
            return self.getToken(RustiQParser.LPAREN, 0)

        def RPAREN(self):
            return self.getToken(RustiQParser.RPAREN, 0)

        def block(self):
            return self.getTypedRuleContext(RustiQParser.BlockContext,0)


        def ARROW(self):
            return self.getToken(RustiQParser.ARROW, 0)

        def I32(self):
            return self.getToken(RustiQParser.I32, 0)

        def getRuleIndex(self):
            return RustiQParser.RULE_functionDecl

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitFunctionDecl" ):
                return visitor.visitFunctionDecl(self)
            else:
                return visitor.visitChildren(self)




    def functionDecl(self):

        localctx = RustiQParser.FunctionDeclContext(self, self._ctx, self.state)
        self.enterRule(localctx, 2, self.RULE_functionDecl)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 18
            self.match(RustiQParser.FN)
            self.state = 19
            self.match(RustiQParser.IDENT)
            self.state = 20
            self.match(RustiQParser.LPAREN)
            self.state = 21
            self.match(RustiQParser.RPAREN)
            self.state = 24
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            if _la==8:
                self.state = 22
                self.match(RustiQParser.ARROW)
                self.state = 23
                self.match(RustiQParser.I32)


            self.state = 26
            self.block()
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class BlockContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def LBRACE(self):
            return self.getToken(RustiQParser.LBRACE, 0)

        def RBRACE(self):
            return self.getToken(RustiQParser.RBRACE, 0)

        def statement(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(RustiQParser.StatementContext)
            else:
                return self.getTypedRuleContext(RustiQParser.StatementContext,i)


        def getRuleIndex(self):
            return RustiQParser.RULE_block

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitBlock" ):
                return visitor.visitBlock(self)
            else:
                return visitor.visitChildren(self)




    def block(self):

        localctx = RustiQParser.BlockContext(self, self._ctx, self.state)
        self.enterRule(localctx, 4, self.RULE_block)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 28
            self.match(RustiQParser.LBRACE)
            self.state = 32
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            while _la==2:
                self.state = 29
                self.statement()
                self.state = 34
                self._errHandler.sync(self)
                _la = self._input.LA(1)

            self.state = 35
            self.match(RustiQParser.RBRACE)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class StatementContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def RETURN(self):
            return self.getToken(RustiQParser.RETURN, 0)

        def expression(self):
            return self.getTypedRuleContext(RustiQParser.ExpressionContext,0)


        def SEMICOLON(self):
            return self.getToken(RustiQParser.SEMICOLON, 0)

        def getRuleIndex(self):
            return RustiQParser.RULE_statement

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitStatement" ):
                return visitor.visitStatement(self)
            else:
                return visitor.visitChildren(self)




    def statement(self):

        localctx = RustiQParser.StatementContext(self, self._ctx, self.state)
        self.enterRule(localctx, 6, self.RULE_statement)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 37
            self.match(RustiQParser.RETURN)
            self.state = 38
            self.expression()
            self.state = 39
            self.match(RustiQParser.SEMICOLON)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class ExpressionContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def INT(self, i:int=None):
            if i is None:
                return self.getTokens(RustiQParser.INT)
            else:
                return self.getToken(RustiQParser.INT, i)

        def PLUS(self, i:int=None):
            if i is None:
                return self.getTokens(RustiQParser.PLUS)
            else:
                return self.getToken(RustiQParser.PLUS, i)

        def getRuleIndex(self):
            return RustiQParser.RULE_expression

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitExpression" ):
                return visitor.visitExpression(self)
            else:
                return visitor.visitChildren(self)




    def expression(self):

        localctx = RustiQParser.ExpressionContext(self, self._ctx, self.state)
        self.enterRule(localctx, 8, self.RULE_expression)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 41
            self.match(RustiQParser.INT)
            self.state = 46
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            while _la==10:
                self.state = 42
                self.match(RustiQParser.PLUS)
                self.state = 43
                self.match(RustiQParser.INT)
                self.state = 48
                self._errHandler.sync(self)
                _la = self._input.LA(1)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx





