grammar RustiQ;

program
    : functionDecl* EOF
    ;

functionDecl
    : FN IDENT LPAREN RPAREN (ARROW type)? block
    ;

type
    : I32
    | F64
    | BOOL
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
    : LET MUT? IDENT (COLON type)? (ASSIGN expression)? SEMICOLON
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
    | FLOAT
    | TRUE
    | FALSE
    | IDENT
    | LPAREN expression RPAREN
    ;

// Palabras reservadas
FN     : 'fn';
RETURN : 'return';
LET    : 'let';
MUT    : 'mut';

I32    : 'i32';
F64    : 'f64';
BOOL   : 'bool';

TRUE   : 'true';
FALSE  : 'false';

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

// Identificadores y literales
IDENT : [a-zA-Z_] [a-zA-Z_0-9]*;
FLOAT : [0-9]+ '.' [0-9]+;
INT   : [0-9]+;

// Comentarios y espacios
LINE_COMMENT  : '//' ~[\r\n]* -> skip;
BLOCK_COMMENT : '/*' .*? '*/' -> skip;
WS            : [ \t\r\n]+ -> skip;