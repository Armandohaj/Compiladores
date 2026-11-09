grammar RustiQ;

// =====================================================
// 1. PROGRAMA, FUNCIONES Y TIPOS
// =====================================================

// Un programa contiene cero o más funciones.
// EOF exige consumir todo el archivo.
program
    : functionDecl* EOF
    ;

// Funciones sin parámetros en esta etapa.
// El tipo de retorno es opcional.
functionDecl
    : FN IDENT LPAREN RPAREN (ARROW type)? block
    ;

// Tipos incorporados hasta ahora.
type
    : I32
    | F64
    | BOOL
    ;

// =====================================================
// 2. BLOQUES Y SENTENCIAS
// =====================================================

// Un bloque contiene sentencias entre llaves.
block
    : LBRACE statement* RBRACE
    ;

// Instrucciones disponibles dentro de un bloque.
statement
    : letDecl
    | assignment SEMICOLON
    | returnStmt
    | ifStmt
    | block
    ;

// Declaración de variable.
// Mutabilidad, tipo e inicializador opcionales.
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

// Condicional:
// if condición { ... }
// if condición { ... } else { ... }
// if condición { ... } else if condición { ... }
//
// El análisis semántico comprobará que la condición sea bool.
// El else es opcional y puede contener un bloque u otro if.
ifStmt
    : IF expression block (ELSE (block | ifStmt))?
    ;

// =====================================================
// 3. EXPRESIONES Y PRIORIDAD
// =====================================================

expression
    : logicalOr
    ;

// O lógico: menor prioridad que &&.
logicalOr
    : logicalAnd (OR logicalAnd)*
    ;

// Y lógico.
logicalAnd
    : comparison (AND comparison)*
    ;

// Una comparación opcional entre expresiones aritméticas.
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
// Tienen mayor prioridad que suma y resta.
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

// Deben aparecer antes de IDENT para distinguirlas
// de los nombres de variables y funciones.
FN     : 'fn';
RETURN : 'return';
LET    : 'let';
MUT    : 'mut';
IF     : 'if';
ELSE   : 'else';

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

// Nombre que comienza con letra o guion bajo.
IDENT
    : [a-zA-Z_] [a-zA-Z_0-9]*
    ;

// Decimal con dígitos antes y después del punto.
FLOAT
    : [0-9]+ '.' [0-9]+
    ;

// Entero sin signo: el negativo se reconoce en unary.
INT
    : [0-9]+
    ;

// =====================================================
// 7. COMENTARIOS Y ESPACIOS
// =====================================================

// -> skip evita enviar estos tokens al parser.
LINE_COMMENT
    : '//' ~[\r\n]* -> skip
    ;

// Comentarios de bloque sin anidamiento.
BLOCK_COMMENT
    : '/*' .*? '*/' -> skip
    ;

// Espacios, tabulaciones y saltos de línea.
WS
    : [ \t\r\n]+ -> skip
    ;