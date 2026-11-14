# Generated from RustiQ.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .RustiQParser import RustiQParser
else:
    from RustiQParser import RustiQParser

# This class defines a complete generic visitor for a parse tree produced by RustiQParser.

class RustiQVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by RustiQParser#program.
    def visitProgram(self, ctx:RustiQParser.ProgramContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#structDecl.
    def visitStructDecl(self, ctx:RustiQParser.StructDeclContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#fieldDecl.
    def visitFieldDecl(self, ctx:RustiQParser.FieldDeclContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#constDecl.
    def visitConstDecl(self, ctx:RustiQParser.ConstDeclContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#functionDecl.
    def visitFunctionDecl(self, ctx:RustiQParser.FunctionDeclContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#parameterList.
    def visitParameterList(self, ctx:RustiQParser.ParameterListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#parameter.
    def visitParameter(self, ctx:RustiQParser.ParameterContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#type.
    def visitType(self, ctx:RustiQParser.TypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#block.
    def visitBlock(self, ctx:RustiQParser.BlockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#statement.
    def visitStatement(self, ctx:RustiQParser.StatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#letDecl.
    def visitLetDecl(self, ctx:RustiQParser.LetDeclContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#assignment.
    def visitAssignment(self, ctx:RustiQParser.AssignmentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#indexAccess.
    def visitIndexAccess(self, ctx:RustiQParser.IndexAccessContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#tupleAccess.
    def visitTupleAccess(self, ctx:RustiQParser.TupleAccessContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#fieldAccess.
    def visitFieldAccess(self, ctx:RustiQParser.FieldAccessContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#assignmentOp.
    def visitAssignmentOp(self, ctx:RustiQParser.AssignmentOpContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#returnStmt.
    def visitReturnStmt(self, ctx:RustiQParser.ReturnStmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#ifStmt.
    def visitIfStmt(self, ctx:RustiQParser.IfStmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#whileStmt.
    def visitWhileStmt(self, ctx:RustiQParser.WhileStmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#loopStmt.
    def visitLoopStmt(self, ctx:RustiQParser.LoopStmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#breakStmt.
    def visitBreakStmt(self, ctx:RustiQParser.BreakStmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#continueStmt.
    def visitContinueStmt(self, ctx:RustiQParser.ContinueStmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#functionCall.
    def visitFunctionCall(self, ctx:RustiQParser.FunctionCallContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#argumentList.
    def visitArgumentList(self, ctx:RustiQParser.ArgumentListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#expression.
    def visitExpression(self, ctx:RustiQParser.ExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#logicalOr.
    def visitLogicalOr(self, ctx:RustiQParser.LogicalOrContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#logicalAnd.
    def visitLogicalAnd(self, ctx:RustiQParser.LogicalAndContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#comparison.
    def visitComparison(self, ctx:RustiQParser.ComparisonContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#relOp.
    def visitRelOp(self, ctx:RustiQParser.RelOpContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#additive.
    def visitAdditive(self, ctx:RustiQParser.AdditiveContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#multiplicative.
    def visitMultiplicative(self, ctx:RustiQParser.MultiplicativeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#unary.
    def visitUnary(self, ctx:RustiQParser.UnaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#postfix.
    def visitPostfix(self, ctx:RustiQParser.PostfixContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#primary.
    def visitPrimary(self, ctx:RustiQParser.PrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#structLiteral.
    def visitStructLiteral(self, ctx:RustiQParser.StructLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#fieldInit.
    def visitFieldInit(self, ctx:RustiQParser.FieldInitContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#tupleLiteral.
    def visitTupleLiteral(self, ctx:RustiQParser.TupleLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by RustiQParser#arrayLiteral.
    def visitArrayLiteral(self, ctx:RustiQParser.ArrayLiteralContext):
        return self.visitChildren(ctx)



del RustiQParser