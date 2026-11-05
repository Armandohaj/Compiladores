grammar RustiQ;

program
    : functionDecl* EOF
    ;

functionDecl
    : FN IDENT LPAREN RPAREN (ARROW I32)? block
    ;

block
    : LBRACE statement* RBRACE
    ;

statement
    : letDecl
    | assignment SEMICOLON
    | returnStmt
    | block
    ;

letDecl
    : LET MUT? IDENT (COLON I32)? (ASSIGN expression)? SEMICOLON
    ;

assignment
    : IDENT ASSIGN expression
    ;

returnStmt
    : RETURN expression? SEMICOLON
    ;

expression
    : additive
    ;

additive
    : multiplicative ((PLUS | MINUS) multiplicative)*
    ;

multiplicative
    : unary ((STAR | SLASH | PERCENT) unary)*
    ;

unary
    : MINUS? primary
    ;

primary
    : INT
    | IDENT
    | LPAREN expression RPAREN
    ;

// Palabras reservadas
FN     : 'fn';
RETURN : 'return';
LET    : 'let';
MUT    : 'mut';
I32    : 'i32';

// Símbolos
LPAREN    : '(';
RPAREN    : ')';
LBRACE    : '{';
RBRACE    : '}';
ARROW     : '->';
SEMICOLON : ';';
COLON     : ':';
ASSIGN    : '=';
PLUS      : '+';
MINUS     : '-';
STAR      : '*';
SLASH     : '/';
PERCENT   : '%';

// Identificadores y números enteros
IDENT : [a-zA-Z_] [a-zA-Z_0-9]*;
INT   : [0-9]+;

// Comentarios y espacios
LINE_COMMENT  : '//' ~[\r\n]* -> skip;
BLOCK_COMMENT : '/*' .*? '*/' -> skip;
WS            : [ \t\r\n]+ -> skip;