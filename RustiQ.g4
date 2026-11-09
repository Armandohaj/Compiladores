grammar RustiQ;

// =====================================================
// 1. PROGRAMA, FUNCIONES Y TIPOS
// =====================================================

// Un programa contiene cero o más funciones.
// EOF exige consumir todo el archivo.
program
    : functionDecl* EOF
    ;

// Funciones sin parámetros por ahora.
// El tipo de retorno es opcional.
functionDecl
    : FN IDENT LPAREN RPAREN (ARROW type)? block
    ;

// Tipos disponibles.
type
    : I32
    | F64
    | BOOL
    ;

// =====================================================
// 2. BLOQUES Y SENTENCIAS
// =====================================================

// Grupo de sentencias entre llaves.
block
    : LBRACE statement* RBRACE
    ;

// Instrucciones disponibles dentro de un bloque.
statement
    : letDecl
    | assignment SEMICOLON
    | returnStmt
    | ifStmt
    | whileStmt
    | breakStmt
    | continueStmt
    | block
    ;

// Variable con mutabilidad, tipo e inicializador opcionales.
letDecl
    : LET MUT? IDENT (COLON type)? (ASSIGN expression)? SEMICOLON
    ;

// Asignación a una variable.
// El punto y coma se reconoce en statement.
assignment
    : IDENT ASSIGN expression
    ;

// Retorno con o sin valor.
returnStmt
    : RETURN expression? SEMICOLON
    ;

// Condicional con else o else if opcional.
ifStmt
    : IF expression block (ELSE (block | ifStmt))?
    ;

// Repite un bloque mientras la condición sea verdadera.
// Ejemplo: while contador < 10 { ... }
//
// La condición debe ser bool.
// Esa comprobación corresponde al análisis semántico.
whileStmt
    : WHILE expression block
    ;

// Sale del ciclo más cercano.
// La semántica comprobará que esté dentro de un ciclo.
breakStmt
    : BREAK SEMICOLON
    ;

// Pasa a la siguiente iteración del ciclo más cercano.
// La semántica comprobará que esté dentro de un ciclo.
continueStmt
    : CONTINUE SEMICOLON
    ;

// =====================================================
// 3. EXPRESIONES Y PRIORIDAD
// =====================================================

expression
    : logicalOr
    ;

// O lógico.
logicalOr
    : logicalAnd (OR logicalAnd)*
    ;

// Y lógico: mayor prioridad que ||.
logicalAnd
    : comparison (AND comparison)*
    ;

// Comparación opcional entre expresiones aritméticas.
comparison
    : additive (relOp additive)?
    ;

// Operadores de comparación.
relOp
    : EQ
    | NEQ
    | LT
    | LE
    | GT
    | GE
    ;

// Suma y resta.
additive
    : multiplicative ((PLUS | MINUS) multiplicative)*
    ;

// Multiplicación, división y residuo.
// Mayor prioridad que suma y resta.
multiplicative
    : unary ((STAR | SLASH | PERCENT) unary)*
    ;

// Signo negativo o negación lógica opcional.
unary
    : (MINUS | NOT)? primary
    ;

// Valores básicos y expresiones entre paréntesis.
primary
    : INT
    | FLOAT
    | TRUE
    | FALSE
    | IDENT
    | LPAREN expression RPAREN
    ;

// =====================================================
// 4. PALABRAS RESERVADAS
// =====================================================

// Se colocan antes de IDENT para distinguirlas
// de los nombres de variables y funciones.
FN       : 'fn';
RETURN   : 'return';
LET      : 'let';
MUT      : 'mut';
IF       : 'if';
ELSE     : 'else';
WHILE    : 'while';
BREAK    : 'break';
CONTINUE : 'continue';

I32    : 'i32';
F64    : 'f64';
BOOL   : 'bool';

TRUE   : 'true';
FALSE  : 'false';

// =====================================================
// 5. SÍMBOLOS Y OPERADORES
// =====================================================

LPAREN    : '(';
RPAREN    : ')';
LBRACE    : '{';
RBRACE    : '}';
ARROW     : '->';
SEMICOLON : ';';
COLON     : ':';

// Comparaciones.
EQ     : '==';
NEQ    : '!=';
LE     : '<=';
GE     : '>=';
LT     : '<';
GT     : '>';

// Operadores lógicos.
AND    : '&&';
OR     : '||';
NOT    : '!';

// Asignación y aritmética.
ASSIGN  : '=';
PLUS    : '+';
MINUS   : '-';
STAR    : '*';
SLASH   : '/';
PERCENT : '%';

// =====================================================
// 6. IDENTIFICADORES Y LITERALES
// =====================================================

// Nombres que comienzan con una letra o guion bajo.
IDENT
    : [a-zA-Z_] [a-zA-Z_0-9]*
    ;

// Decimales con dígitos antes y después del punto.
FLOAT
    : [0-9]+ '.' [0-9]+
    ;

// Enteros sin signo.
// El signo negativo se reconoce en unary.
INT
    : [0-9]+
    ;

// =====================================================
// 7. COMENTARIOS Y ESPACIOS
// =====================================================

// Ignorar comentarios de línea.
LINE_COMMENT
    : '//' ~[\r\n]* -> skip
    ;

// Ignorar comentarios de bloque sin anidamiento.
BLOCK_COMMENT
    : '/*' .*? '*/' -> skip
    ;

// Ignorar espacios, tabulaciones y saltos de línea.
WS
    : [ \t\r\n]+ -> skip
    ;