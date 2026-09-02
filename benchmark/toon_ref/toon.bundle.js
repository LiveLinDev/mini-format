/* TOON reference implementation (https://github.com/toon-format/toon, MIT) — browser bundle built from the TypeScript sources with Node's type stripping. Global: TOON */
var TOON = (function(){
const __defs = {};
const __cache = {};
function __require(id){ if (__cache[id]) return __cache[id]; const m = {exports:{}}; __cache[id] = m.exports; __defs[id](m.exports, m); return m.exports; }
__defs['constants.ts'] = function(exports, module){
// #region List markers

const LIST_ITEM_MARKER = '-'
const LIST_ITEM_PREFIX = '- '

// #endregion

// #region Structural characters

const COMMA = ','
const COLON = ':'
const SPACE = ' '
const PIPE = '|'
const COMMENT_MARKER = '#'

// #endregion

// #region Brackets and braces

const OPEN_BRACKET = '['
const CLOSE_BRACKET = ']'
const OPEN_BRACE = '{'
const CLOSE_BRACE = '}'

// #endregion

// #region Literals

const NULL_LITERAL = 'null'
const TRUE_LITERAL = 'true'
const FALSE_LITERAL = 'false'

// #endregion

// #region Escape characters

const BACKSLASH = '\\'
const DOUBLE_QUOTE = '"'
const NEWLINE = '\n'
const CARRIAGE_RETURN = '\r'
const TAB = '\t'
const BYTE_ORDER_MARK = '﻿'

// #endregion

// #region Delimiters

const DELIMITERS = {
  comma: COMMA       ,
  tab: TAB        ,
  pipe: PIPE       ,
}         

                                                  
                                                       

const DEFAULT_DELIMITER            = DELIMITERS.comma

// #endregion

exports.LIST_ITEM_MARKER = LIST_ITEM_MARKER;
exports.LIST_ITEM_PREFIX = LIST_ITEM_PREFIX;
exports.COMMA = COMMA;
exports.COLON = COLON;
exports.SPACE = SPACE;
exports.PIPE = PIPE;
exports.COMMENT_MARKER = COMMENT_MARKER;
exports.OPEN_BRACKET = OPEN_BRACKET;
exports.CLOSE_BRACKET = CLOSE_BRACKET;
exports.OPEN_BRACE = OPEN_BRACE;
exports.CLOSE_BRACE = CLOSE_BRACE;
exports.NULL_LITERAL = NULL_LITERAL;
exports.TRUE_LITERAL = TRUE_LITERAL;
exports.FALSE_LITERAL = FALSE_LITERAL;
exports.BACKSLASH = BACKSLASH;
exports.DOUBLE_QUOTE = DOUBLE_QUOTE;
exports.NEWLINE = NEWLINE;
exports.CARRIAGE_RETURN = CARRIAGE_RETURN;
exports.TAB = TAB;
exports.BYTE_ORDER_MARK = BYTE_ORDER_MARK;
exports.DELIMITERS = DELIMITERS;
exports.DEFAULT_DELIMITER = DEFAULT_DELIMITER;
};
__defs['decode/decoders.ts'] = function(exports, module){
                                                                                                                                     
                                                            
                                                         
const { COLON, DEFAULT_DELIMITER, LIST_ITEM_MARKER, LIST_ITEM_PREFIX } = __require('constants.ts');
const { findClosingQuote, findUnquotedChar, trimSpaces } = __require('shared/string-utils.ts');
const { ToonDecodeError, withLine } = __require('decode/errors.ts');
const { createLineReader, driveAsync, driveSync, peekLine, readLine } = __require('decode/line-reader.ts');
const { countLeafFields, isArrayHeaderContent, isKeyValueContent, mapRowValuesToPrimitives, parseArrayHeaderLine, parseDelimitedValues, parseKeyToken, parsePrimitiveToken } = __require('decode/parser.ts');
const { assertExpectedCount, isDataRow, validateNoBlankLinesInRange, validateNoExtraListItems, validateNoExtraTabularRows } = __require('decode/validation.ts');

                                                                

function resolveContext(options                      )                 {
  return {
    indentSize: options?.indentSize ?? options?.indent ?? 2,
    strict: options?.strict ?? true,
  }
}

// #region Public entry points

function decodeStreamSync(
  source                  ,
  options                      ,
)                             {
  const resolvedOptions = resolveContext(options)
  const reader = createLineReader(resolvedOptions)
  return driveSync(source, decodeDocument(reader, resolvedOptions))
}

function decodeStream(
  source                                          ,
  options                      ,
)                                  {
  const resolvedOptions = resolveContext(options)
  const reader = createLineReader(resolvedOptions)
  return driveAsync(source, decodeDocument(reader, resolvedOptions))
}

// #endregion

// #region Document dispatch

function* decodeDocument(reader            , options                )           {
  const first = yield* peekLine(reader)
  if (!first) {
    yield { type: 'startObject' }
    yield { type: 'endObject' }
    return
  }

  if (trimSpaces(first.content) === '[]') {
    yield* readLine(reader)
    yield { type: 'startArray', length: 0 }
    yield { type: 'endArray' }
    yield* assertFullyConsumed(reader, options.strict)
    return
  }

  if (isArrayHeaderContent(first.content)) {
    const headerInfo = withLine(first, () => resolveArrayHeader(parseArrayHeaderLine(first.content, DEFAULT_DELIMITER), options.strict))
    if (headerInfo) {
      yield* readLine(reader)
      yield* decodeArrayFromHeader(headerInfo.header, headerInfo.inlineValues, reader, 0, options, first)
      yield* assertFullyConsumed(reader, options.strict)
      return
    }
  }

  yield* readLine(reader)
  const following = yield* peekLine(reader)
  const hasMore = following !== undefined
  if (!hasMore && !isKeyValueLine(first)) {
    yield { type: 'primitive', value: withLine(first, () => parsePrimitiveToken(first.content)) }
    return
  }

  if (!isKeyValueLine(first) && following?.depth === 0) {
    throw new ToonDecodeError(
      'Top-level document must start with a key-value or array-header line',
      { line: first.lineNumber, source: first.raw },
    )
  }

  const rootSeenKeys = options.strict ? new Set        () : undefined
  yield { type: 'startObject' }
  yield* decodeKeyValue(first, reader, 0, options, rootSeenKeys)

  while (true) {
    const line = yield* peekLine(reader)
    if (!line) {
      break
    }

    if (line.depth !== 0) {
      if (options.strict) {
        throw overIndentedLineError(line, 0)
      }
      assertNotScalarLine(line)
      yield* readLine(reader)
      continue
    }

    yield* readLine(reader)
    yield* decodeKeyValue(line, reader, 0, options, rootSeenKeys)
  }

  yield { type: 'endObject' }
}

// #endregion

// #region Error helpers

function assertNoDepthJump(firstNestedLine            , parentDepth       , strict         )       {
  if (strict && firstNestedLine.depth > parentDepth + 1) {
    throw new ToonDecodeError(
      `Indentation depth jump: expected depth ${parentDepth + 1}, but found ${firstNestedLine.depth}`,
      { line: firstNestedLine.lineNumber, source: firstNestedLine.raw },
    )
  }
}

function overIndentedLineError(line            , expectedDepth       )                  {
  return new ToonDecodeError(
    `Over-indented line: expected depth ${expectedDepth}, but found ${line.depth}`,
    { line: line.lineNumber, source: line.raw },
  )
}

// Both modes reject a bare token outside root primitive position, so it must not reach
// the non-strict paths that drop an over-indented line.
function assertNotScalarLine(line            )       {
  const isListItem = line.content.startsWith(LIST_ITEM_PREFIX) || line.content === LIST_ITEM_MARKER
  if (isListItem || findUnquotedChar(line.content, COLON) !== -1) {
    return
  }

  throw new ToonDecodeError(
    'Unexpected bare token line outside root primitive position',
    { line: line.lineNumber, source: line.raw },
  )
}

function keylessKeyedError(line            )                  {
  return new ToonDecodeError(
    'Keyless keyed header is only valid at the document root',
    { line: line.lineNumber, source: line.raw },
  )
}

function keylessHeaderError(line            )                  {
  return new ToonDecodeError(
    'Keyless array header is only valid at the document root or as a list item',
    { line: line.lineNumber, source: line.raw },
  )
}

function keylessFieldsHeaderError(line            )                  {
  return new ToonDecodeError(
    'Keyless header with a field list is only valid at the document root',
    { line: line.lineNumber, source: line.raw },
  )
}

// Strict decoding never silently discards input, so a line after the root form is an error.
function* assertFullyConsumed(reader            , strict         )           {
  if (!strict) {
    return
  }
  const line = yield* peekLine(reader)
  if (line) {
    throw new ToonDecodeError(
      'Unexpected content after the document root',
      { line: line.lineNumber, source: line.raw },
    )
  }
}

function assertNoDuplicateKey(key        , line            , seenKeys                         )       {
  if (!seenKeys)
    return
  if (seenKeys.has(key)) {
    throw new ToonDecodeError(
      `Duplicate sibling key "${key}"`,
      { line: line.lineNumber, source: line.raw },
    )
  }
  seenKeys.add(key)
}

// #endregion

// #region Decode rules

function* decodeKeyValue(
  line            ,
  reader            ,
  baseDepth       ,
  options                ,
  seenKeys              ,
)           {
  const content = line.content

  const arrayHeader = withLine(line, () => resolveArrayHeader(parseArrayHeaderLine(content, DEFAULT_DELIMITER), options.strict))
  if (arrayHeader && arrayHeader.header.key !== undefined) {
    assertNoDuplicateKey(arrayHeader.header.key, line, seenKeys)
    yield { type: 'key', key: arrayHeader.header.key }
    yield* decodeArrayFromHeader(arrayHeader.header, arrayHeader.inlineValues, reader, baseDepth, options, line)
    return
  }

  if (arrayHeader && arrayHeader.header.key === undefined && options.strict) {
    throw arrayHeader.header.keyed ? keylessKeyedError(line) : keylessHeaderError(line)
  }

  const { key, end } = withLine(line, () => parseKeyToken(content, 0))
  const rest = trimSpaces(content.slice(end))

  assertNoDuplicateKey(key, line, seenKeys)
  yield { type: 'key', key }

  if (!rest) {
    const nextLine = yield* peekLine(reader)
    if (nextLine && nextLine.depth > baseDepth) {
      assertNoDepthJump(nextLine, baseDepth, options.strict)
      yield { type: 'startObject' }
      yield* decodeObjectFields(reader, baseDepth + 1, options)
      yield { type: 'endObject' }
      return
    }

    yield { type: 'startObject' }
    yield { type: 'endObject' }
    return
  }

  if (rest === '[]') {
    yield { type: 'startArray', length: 0 }
    yield { type: 'endArray' }
    return
  }

  yield { type: 'primitive', value: withLine(line, () => parsePrimitiveToken(rest)) }
}

function* decodeObjectFields(
  reader            ,
  baseDepth       ,
  options                ,
)           {
  let computedDepth                   
  const seenKeys = options.strict ? new Set        () : undefined

  while (true) {
    const line = yield* peekLine(reader)
    if (!line || line.depth < baseDepth) {
      break
    }

    if (computedDepth === undefined && line.depth >= baseDepth) {
      computedDepth = line.depth
    }

    if (line.depth === computedDepth) {
      yield* readLine(reader)
      yield* decodeKeyValue(line, reader, computedDepth, options, seenKeys)
    }
    else if (computedDepth !== undefined && line.depth > computedDepth) {
      if (options.strict) {
        throw overIndentedLineError(line, computedDepth)
      }
      assertNotScalarLine(line)
      yield* readLine(reader)
    }
    else {
      break
    }
  }
}

function* decodeArrayFromHeader(
  header                 ,
  inlineValues                    ,
  reader            ,
  baseDepth       ,
  options                ,
  headerLine            ,
)           {
  // Keyed tabular header: decodes to an object, not an array.
  if (header.keyed) {
    yield* decodeKeyedObject(header, reader, baseDepth, options, headerLine)
    return
  }

  yield { type: 'startArray', length: header.length }

  if (inlineValues) {
    yield* decodeInlinePrimitiveArray(header, inlineValues, options, headerLine)
    yield { type: 'endArray' }
    return
  }

  if (header.fields && header.fields.length > 0) {
    yield* decodeTabularArray(header, reader, baseDepth, options, headerLine)
    yield { type: 'endArray' }
    return
  }

  yield* decodeListArray(header, reader, baseDepth, options, headerLine)
  yield { type: 'endArray' }
}

function* decodeInlinePrimitiveArray(
  header                 ,
  inlineValues        ,
  options                ,
  headerLine            ,
)                             {
  if (!trimSpaces(inlineValues)) {
    assertExpectedCount(0, header.length, 'inline-form values', options, headerLine)
    return
  }

  const values = withLine(headerLine, () => parseDelimitedValues(inlineValues, header.delimiter))
  const primitives = withLine(headerLine, () => mapRowValuesToPrimitives(values))

  assertExpectedCount(primitives.length, header.length, 'inline-form values', options, headerLine)

  for (const primitive of primitives) {
    yield { type: 'primitive', value: primitive }
  }
}

function* decodeKeyedObject(
  header                 ,
  reader            ,
  baseDepth       ,
  options                ,
  headerLine            ,
)           {
  const entryDepth = baseDepth + 1
  const leafFieldCount = countLeafFields(header.fields )
  const seenEntryKeys = options.strict ? new Set        () : undefined
  let entryCount = 0
  let startLine                    
  let endLine                    
  let lastEntryLine             = headerLine

  yield { type: 'startObject' }

  // A keyed scope ends only by dedent or end of input, so every line at entry depth
  // carrying an unquoted colon is an entry row.
  while (true) {
    const line = yield* peekLine(reader)
    if (!line || line.depth <= baseDepth) {
      break
    }

    if (line.depth > entryDepth) {
      if (options.strict) {
        throw new ToonDecodeError(
          'Unexpected indentation inside keyed tabular object',
          { line: line.lineNumber, source: line.raw },
        )
      }
      yield* readLine(reader)
      continue
    }

    if (findUnquotedChar(line.content, COLON) === -1) {
      if (options.strict) {
        throw new ToonDecodeError(
          'Expected entry row inside keyed tabular object',
          { line: line.lineNumber, source: line.raw },
        )
      }
      yield* readLine(reader)
      continue
    }

    yield* readLine(reader)
    if (startLine === undefined) {
      startLine = line.lineNumber
    }
    endLine = line.lineNumber
    lastEntryLine = line

    const { key, end } = withLine(line, () => parseKeyToken(line.content, 0))
    assertNoDuplicateKey(key, line, seenEntryKeys)
    yield { type: 'key', key }

    const cellsContent = trimSpaces(line.content.slice(end))
    const values = cellsContent === ''
      ? []
      : withLine(line, () => parseDelimitedValues(cellsContent, header.delimiter))
    assertExpectedCount(values.length, leafFieldCount, 'keyed entry cells', options, line)

    const primitives = withLine(line, () => mapRowValuesToPrimitives(values))
    yield* yieldObjectFromFields(header.fields , primitives)

    entryCount++
  }

  assertExpectedCount(entryCount, header.length, 'keyed entries', options, lastEntryLine)

  if (options.strict && startLine !== undefined && endLine !== undefined) {
    validateNoBlankLinesInRange(startLine, endLine, reader.scanState.blankLines, options.strict, 'keyed tabular object')
  }

  yield { type: 'endObject' }
}

function* decodeTabularArray(
  header                 ,
  reader            ,
  baseDepth       ,
  options                ,
  headerLine            ,
)           {
  const rowDepth = baseDepth + 1
  let rowCount = 0
  let startLine                    
  let endLine                    
  let lastRowLine             = headerLine

  // Only strict stops at N, leaving the surplus to `validateNoExtraTabularRows`; non-strict reads on so [N] never truncates.
  while (!options.strict || rowCount < header.length) {
    const line = yield* peekLine(reader)
    if (!line || line.depth < rowDepth) {
      break
    }

    if (line.depth === rowDepth) {
      if (!isDataRow(line.content, header.delimiter)) {
        break
      }

      if (startLine === undefined) {
        startLine = line.lineNumber
      }
      endLine = line.lineNumber
      lastRowLine = line

      yield* readLine(reader)
      const values = withLine(line, () => parseDelimitedValues(line.content, header.delimiter))
      assertExpectedCount(values.length, countLeafFields(header.fields ), 'tabular row values', options, line)

      const primitives = withLine(line, () => mapRowValuesToPrimitives(values))
      yield* yieldObjectFromFields(header.fields , primitives)

      rowCount++
    }
    else {
      break
    }
  }

  assertExpectedCount(rowCount, header.length, 'tabular rows', options, lastRowLine)

  if (options.strict && startLine !== undefined && endLine !== undefined) {
    validateNoBlankLinesInRange(startLine, endLine, reader.scanState.blankLines, options.strict, 'tabular array')
  }

  if (options.strict) {
    const nextLine = yield* peekLine(reader)
    validateNoExtraTabularRows(nextLine, rowDepth, header)
  }
}

function* decodeListArray(
  header                 ,
  reader            ,
  baseDepth       ,
  options                ,
  headerLine            ,
)           {
  const itemDepth = baseDepth + 1
  let itemCount = 0
  let startLine                    
  let endLine                    
  let lastItemLine             = headerLine

  // Only strict stops at N, leaving the surplus to `validateNoExtraListItems`; non-strict reads on so [N] never truncates.
  while (!options.strict || itemCount < header.length) {
    const line = yield* peekLine(reader)
    if (!line || line.depth < itemDepth) {
      break
    }

    const isListItem = line.content.startsWith(LIST_ITEM_PREFIX) || line.content === LIST_ITEM_MARKER

    if (line.depth === itemDepth && isListItem) {
      if (startLine === undefined) {
        startLine = line.lineNumber
      }
      endLine = line.lineNumber
      lastItemLine = line

      yield* decodeListItem(reader, itemDepth, options)

      const lastConsumedLine = reader.lastLine
      if (lastConsumedLine) {
        endLine = lastConsumedLine.lineNumber
        lastItemLine = lastConsumedLine
      }

      itemCount++
    }
    else {
      break
    }
  }

  assertExpectedCount(itemCount, header.length, 'list-form items', options, lastItemLine)

  if (options.strict && startLine !== undefined && endLine !== undefined) {
    validateNoBlankLinesInRange(startLine, endLine, reader.scanState.blankLines, options.strict, 'list-form array')
  }

  if (options.strict) {
    const nextLine = yield* peekLine(reader)
    validateNoExtraListItems(nextLine, itemDepth, header.length)
  }
}

function* decodeListItem(
  reader            ,
  baseDepth       ,
  options                ,
)           {
  const line = yield* readLine(reader)
  if (!line) {
    throw new ReferenceError('Expected list item')
  }

  let afterHyphen        

  if (line.content === LIST_ITEM_MARKER) {
    yield { type: 'startObject' }
    yield { type: 'endObject' }
    return
  }
  else if (line.content.startsWith(LIST_ITEM_PREFIX)) {
    afterHyphen = line.content.slice(LIST_ITEM_PREFIX.length)
  }
  else {
    throw new ToonDecodeError(
      `Expected list item to start with "${LIST_ITEM_PREFIX}"`,
      { line: line.lineNumber, source: line.raw },
    )
  }

  if (!trimSpaces(afterHyphen)) {
    yield { type: 'startObject' }
    yield { type: 'endObject' }
    return
  }

  if (trimSpaces(afterHyphen) === '[]') {
    yield { type: 'startArray', length: 0 }
    yield { type: 'endArray' }
    return
  }

  const itemLine             = { ...line, content: afterHyphen }

  if (isArrayHeaderContent(afterHyphen)) {
    const arrayHeader = withLine(itemLine, () => resolveArrayHeader(parseArrayHeaderLine(afterHyphen, DEFAULT_DELIMITER), options.strict))
    if (arrayHeader) {
      // There is no keyless keyed or fields-bearing list-item form.
      if (arrayHeader.header.keyed || arrayHeader.header.fields !== undefined) {
        if (options.strict) {
          throw arrayHeader.header.keyed ? keylessKeyedError(itemLine) : keylessFieldsHeaderError(itemLine)
        }
      }
      else {
        yield* decodeArrayFromHeader(arrayHeader.header, arrayHeader.inlineValues, reader, baseDepth, options, itemLine)
        return
      }
    }
  }

  const headerInfo = withLine(itemLine, () => resolveArrayHeader(parseArrayHeaderLine(afterHyphen, DEFAULT_DELIMITER), options.strict))
  if (headerInfo && headerInfo.header.key !== undefined && headerInfo.header.fields !== undefined) {
    const header = headerInfo.header
    const seenKeys = options.strict ? new Set        ([header.key ]) : undefined
    yield { type: 'startObject' }
    yield { type: 'key', key: header.key  }

    // Use `baseDepth + 1` for the array so rows are at `baseDepth + 2`.
    yield* decodeArrayFromHeader(header, headerInfo.inlineValues, reader, baseDepth + 1, options, itemLine)

    yield* followSiblingFields(reader, baseDepth + 1, options, seenKeys)

    yield { type: 'endObject' }
    return
  }

  if (isKeyValueContent(afterHyphen)) {
    const seenKeys = options.strict ? new Set        () : undefined
    yield { type: 'startObject' }
    yield* decodeKeyValue(itemLine, reader, baseDepth + 1, options, seenKeys)

    yield* followSiblingFields(reader, baseDepth + 1, options, seenKeys)

    yield { type: 'endObject' }
    return
  }

  yield { type: 'primitive', value: withLine(itemLine, () => parsePrimitiveToken(afterHyphen)) }
}

function* followSiblingFields(
  reader            ,
  followDepth       ,
  options                ,
  seenKeys              ,
)           {
  while (true) {
    const nextLine = yield* peekLine(reader)
    if (!nextLine || nextLine.depth < followDepth) {
      break
    }

    if (nextLine.depth === followDepth && !nextLine.content.startsWith(LIST_ITEM_PREFIX)) {
      yield* readLine(reader)
      yield* decodeKeyValue(nextLine, reader, followDepth, options, seenKeys)
    }
    else {
      break
    }
  }
}

function isKeyValueLine(line            )          {
  const content = line.content
  if (content.startsWith('"')) {
    const closingQuoteIndex = findClosingQuote(content, 0)
    if (closingQuoteIndex === -1) {
      return false
    }
    return content.slice(closingQuoteIndex + 1).includes(COLON)
  }
  else {
    return content.includes(COLON)
  }
}

// #endregion

// #region Shared decoder helpers

// Keeps the detection/parse split free of error decisions. The bare
// SyntaxError is deliberate: the caller's `withLine` wrapper enriches it into a
// `ToonDecodeError` with a `cause`, matching the direct-throw path.
function resolveArrayHeader(
  result                        ,
  strict         ,
)                                                                 {
  if (result.kind === 'notHeader') {
    return undefined
  }

  if (result.kind === 'invalid') {
    if (strict) {
      throw new SyntaxError(result.reason)
    }
    return undefined
  }

  // A valid header may still carry a strict-only violation that non-strict resolves via LWW.
  if (strict && result.strictError !== undefined) {
    throw new SyntaxError(result.strictError)
  }

  return { header: result.header, inlineValues: result.inlineValues }
}

function* yieldObjectFromFields(
  fields                      ,
  primitives                          ,
)                             {
  let cellIndex = 0

  function* walkFieldGroup(nodes                      )                             {
    yield { type: 'startObject' }
    for (const node of nodes) {
      // A non-strict width mismatch leaves trailing leaf fields with no cell; they are absent, not undefined.
      if (!node.children && cellIndex >= primitives.length) {
        continue
      }

      yield { type: 'key', key: node.name }
      if (node.children) {
        yield* walkFieldGroup(node.children)
      }
      else {
        yield { type: 'primitive', value: primitives[cellIndex++]  }
      }
    }

    yield { type: 'endObject' }
  }

  yield* walkFieldGroup(fields)
}

// #endregion

exports.decodeStreamSync = decodeStreamSync;
exports.decodeStream = decodeStream;
};
__defs['decode/errors.ts'] = function(exports, module){
                                             

/**
 * Error thrown by the TOON decoder when input cannot be parsed.
 *
 * Extends `SyntaxError` so existing `instanceof SyntaxError` checks keep working.
 * Adds structured location fields for programmatic consumers and richer CLI output.
 */
class ToonDecodeError extends SyntaxError {
  /** 1-based line number where the error was detected, if known. */
           line         
  /** Raw source line (including indentation) where the error was detected, if known. */
           source         

  constructor(message        , context                                                      ) {
    const prefix = context?.line !== undefined ? `Line ${context.line}: ` : ''
    super(prefix + message, context?.cause !== undefined ? { cause: context.cause } : undefined)
    this.name = 'ToonDecodeError'
    this.line = context?.line
    this.source = context?.source
  }
}

/**
 * Runs `fn` and re-throws any non-`ToonDecodeError` `Error` as a `ToonDecodeError`
 * with line context attached and the original error preserved as `cause`.
 *
 * Pure parser helpers don't know which line they're parsing; this wrapper is how
 * the streaming decoder enriches their errors.
 */
function withLine   (line            , fn         )    {
  try {
    return fn()
  }
  catch (error) {
    if (error instanceof ToonDecodeError)
      throw error
    if (error instanceof Error) {
      throw new ToonDecodeError(error.message, {
        line: line.lineNumber,
        source: line.raw,
        cause: error,
      })
    }
    throw error
  }
}

exports.ToonDecodeError = ToonDecodeError;
exports.withLine = withLine;
};
__defs['decode/event-builder.ts'] = function(exports, module){
                                                                         
const { setOwnProperty } = __require('shared/object-utils.ts');

// #region Build context types

                 
                                                              
                                         

                      
                       
                             
 

// #endregion

// #region Synchronous AST builder

function buildValueFromEvents(events                           )            {
  const state             = { stack: [], root: undefined }

  for (const event of events) {
    applyEvent(state, event)
  }

  return finalizeState(state)
}

// #endregion

// #region Asynchronous AST builder

async function buildValueFromEventsAsync(events                                )                     {
  const state             = { stack: [], root: undefined }

  for await (const event of events) {
    applyEvent(state, event)
  }

  return finalizeState(state)
}

// #endregion

// #region Shared event handlers

function applyEvent(state            , event                 )       {
  const { stack } = state

  switch (event.type) {
    case 'startObject': {
      const obj             = {}

      if (stack.length === 0) {
        stack.push({ type: 'object', obj })
      }
      else {
        const parent = stack[stack.length - 1] 
        if (parent.type === 'object') {
          if (parent.currentKey === undefined) {
            throw new Error('Object startObject event without preceding key')
          }

          setOwnProperty(parent.obj, parent.currentKey, obj)
          parent.currentKey = undefined
        }
        else if (parent.type === 'array') {
          parent.arr.push(obj)
        }

        stack.push({ type: 'object', obj })
      }

      break
    }

    case 'endObject': {
      if (stack.length === 0) {
        throw new Error('Unexpected endObject event')
      }

      const context = stack.pop() 
      if (context.type !== 'object') {
        throw new Error('Mismatched endObject event')
      }

      if (stack.length === 0) {
        state.root = context.obj
      }

      break
    }

    case 'startArray': {
      const arr              = []

      if (stack.length === 0) {
        stack.push({ type: 'array', arr })
      }
      else {
        const parent = stack[stack.length - 1] 
        if (parent.type === 'object') {
          if (parent.currentKey === undefined) {
            throw new Error('Array startArray event without preceding key')
          }
          setOwnProperty(parent.obj, parent.currentKey, arr)
          parent.currentKey = undefined
        }
        else if (parent.type === 'array') {
          parent.arr.push(arr)
        }

        stack.push({ type: 'array', arr })
      }

      break
    }

    case 'endArray': {
      if (stack.length === 0) {
        throw new Error('Unexpected endArray event')
      }

      const context = stack.pop() 
      if (context.type !== 'array') {
        throw new Error('Mismatched endArray event')
      }

      if (stack.length === 0) {
        state.root = context.arr
      }

      break
    }

    case 'key': {
      if (stack.length === 0) {
        throw new Error('Key event outside of object context')
      }

      const parent = stack[stack.length - 1] 
      if (parent.type !== 'object') {
        throw new Error('Key event outside of object context')
      }

      parent.currentKey = event.key

      break
    }

    case 'primitive': {
      if (stack.length === 0) {
        state.root = event.value
      }
      else {
        const parent = stack[stack.length - 1] 
        if (parent.type === 'object') {
          if (parent.currentKey === undefined) {
            throw new Error('Primitive event without preceding key in object')
          }
          setOwnProperty(parent.obj, parent.currentKey, event.value)
          parent.currentKey = undefined
        }
        else if (parent.type === 'array') {
          parent.arr.push(event.value)
        }
      }

      break
    }
  }
}

function finalizeState(state            )            {
  if (state.stack.length !== 0) {
    throw new Error('Incomplete event stream: unclosed objects or arrays')
  }

  if (state.root === undefined) {
    throw new Error('No root value built from events')
  }

  return state.root
}

// #endregion

exports.buildValueFromEvents = buildValueFromEvents;
exports.buildValueFromEventsAsync = buildValueFromEventsAsync;
};
__defs['decode/line-reader.ts'] = function(exports, module){
                                                              
                                                      
const { createScanState, parseLineIncremental } = __require('decode/scanner.ts');

// #region Fetch-line effect

// Rules yield this instead of touching a source directly, so one rule tree serves
// both sync and async sources.
const FETCH_LINE                = Symbol('fetch-line')

                                                                                               

                                                                                           

// #endregion

// #region Line reader

                             
                      
               
                                  
                               
                    
                 
 

function createLineReader(context                                         )             {
  return {
    buffer: [],
    done: false,
    lastLine: undefined,
    scanState: createScanState(),
    indentSize: context.indentSize,
    strict: context.strict,
  }
}

// At most one line of lookahead, so scanner throws and blank accounting keep
// their original ordering.
function* fillBuffer(reader            )                   {
  while (reader.buffer.length === 0 && !reader.done) {
    const raw = yield FETCH_LINE
    if (raw === undefined) {
      reader.done = true
      return
    }

    const parsedLine = parseLineIncremental(raw, reader.scanState, reader.indentSize, reader.strict)
    if (parsedLine !== undefined) {
      reader.buffer.push(parsedLine)
    }
  }
}

function* peekLine(reader            )                                     {
  yield* fillBuffer(reader)
  return reader.buffer[0]
}

function* readLine(reader            )                                     {
  yield* fillBuffer(reader)
  const line = reader.buffer[0]
  if (line !== undefined) {
    reader.buffer.shift()
    reader.lastLine = line
  }

  return line
}

// #endregion

// #region Drivers

function* driveSync(rawSource                  , rule          )                             {
  const iterator = rawSource[Symbol.iterator]()
  let step = rule.next()

  while (!step.done) {
    if (step.value === FETCH_LINE) {
      const result = iterator.next()
      step = rule.next(result.done ? undefined : result.value)
    }
    else {
      yield step.value
      step = rule.next()
    }
  }
}

// Accepts a sync source too, and pulls exactly one raw line per request so a
// chunk-by-chunk reader still delivers incrementally.
async function* driveAsync(
  rawSource                                          ,
  rule          ,
)                                  {
  const iterator                                           = Symbol.asyncIterator in rawSource
    ? rawSource[Symbol.asyncIterator]()
    : rawSource[Symbol.iterator]()
  let step = rule.next()

  while (!step.done) {
    if (step.value === FETCH_LINE) {
      const result = await iterator.next()
      step = rule.next(result.done ? undefined : result.value)
    }
    else {
      yield step.value
      step = rule.next()
    }
  }
}

// #endregion

exports.FETCH_LINE = FETCH_LINE;
exports.createLineReader = createLineReader;
exports.peekLine = peekLine;
exports.readLine = readLine;
exports.driveSync = driveSync;
exports.driveAsync = driveAsync;
};
__defs['decode/parser.ts'] = function(exports, module){
                                                                                       
const { BACKSLASH, CLOSE_BRACE, CLOSE_BRACKET, COLON, DELIMITERS, DOUBLE_QUOTE, FALSE_LITERAL, NULL_LITERAL, OPEN_BRACE, OPEN_BRACKET, PIPE, TAB, TRUE_LITERAL } = __require('constants.ts');
const { isBooleanOrNullLiteral, isNumericLiteral } = __require('shared/literal-utils.ts');
const { findClosingQuote, findUnquotedChar, trimSpaces, unescapeString } = __require('shared/string-utils.ts');

// #region Array header parsing

                                  
                                                                                              
                           
                                         

/**
 * Detects and parses an array-header line into a typed result, staying free of
 * strict-mode policy: callers decide how to treat `invalid` and `strictError`.
 */
function parseArrayHeaderLine(
  content        ,
  defaultDelimiter           ,
)                         {
  const trimmedToken = content.trimStart()

  let bracketStart = -1

  if (trimmedToken.startsWith(DOUBLE_QUOTE)) {
    const closingQuoteIndex = findClosingQuote(trimmedToken, 0)
    if (closingQuoteIndex === -1) {
      return { kind: 'notHeader' }
    }

    const afterQuote = trimmedToken.slice(closingQuoteIndex + 1)
    if (!afterQuote.startsWith(OPEN_BRACKET)) {
      return { kind: 'notHeader' }
    }

    const leadingWhitespace = content.length - trimmedToken.length
    const keyEndIndex = leadingWhitespace + closingQuoteIndex + 1
    bracketStart = content.indexOf(OPEN_BRACKET, keyEndIndex)
  }
  else {
    bracketStart = findUnquotedChar(content, OPEN_BRACKET)
  }

  if (bracketStart === -1) {
    return { kind: 'notHeader' }
  }

  // A header key can't contain an unquoted colon, so this is a key-value line.
  const firstColonIndex = findUnquotedChar(content, COLON)
  if (firstColonIndex !== -1 && firstColonIndex < bracketStart) {
    return { kind: 'notHeader' }
  }

  const bracketEnd = findUnquotedChar(content, CLOSE_BRACKET, bracketStart)
  if (bracketEnd === -1) {
    return { kind: 'notHeader' }
  }

  let colonIndex = bracketEnd + 1
  let braceEnd = colonIndex

  const braceStart = findUnquotedChar(content, OPEN_BRACE, bracketEnd)
  if (braceStart !== -1 && braceStart < findUnquotedChar(content, COLON, bracketEnd)) {
    const gapBeforeBrace = content.slice(bracketEnd + 1, braceStart)
    if (gapBeforeBrace !== '') {
      const trimmedGap = gapBeforeBrace.trim()
      return {
        kind: 'invalid',
        reason: trimmedGap === ''
          ? `Unexpected whitespace between bracket segment and field list`
          : `Unexpected content "${trimmedGap}" between bracket segment and field list`,
      }
    }

    const foundBraceEnd = findMatchingBrace(content, braceStart)
    if (foundBraceEnd !== -1) {
      braceEnd = foundBraceEnd + 1
    }
  }

  colonIndex = findUnquotedChar(content, COLON, Math.max(bracketEnd, braceEnd))
  if (colonIndex === -1) {
    return { kind: 'notHeader' }
  }

  const gapStart = Math.max(bracketEnd + 1, braceEnd)
  const gapBeforeColon = content.slice(gapStart, colonIndex)
  if (gapBeforeColon !== '') {
    const trimmedGap = gapBeforeColon.trim()
    return {
      kind: 'invalid',
      reason: trimmedGap === ''
        ? `Unexpected whitespace between bracket segment and colon`
        : `Unexpected content "${trimmedGap}" between bracket segment and colon`,
    }
  }

  let key                    
  if (bracketStart > 0) {
    const rawKey = content.slice(0, bracketStart)
    // Trimming here would silently turn `foo [2]:` into a header with key `foo`.
    if (rawKey !== rawKey.trimEnd()) {
      return { kind: 'invalid', reason: 'Unexpected whitespace between key and bracket segment' }
    }
    // Unreachable given the quote and bracket guards above. Leaving it uncaught
    // preserves the both-modes throw instead of adding a non-strict swallow.
    key = rawKey.startsWith(DOUBLE_QUOTE) ? parseStringLiteral(rawKey) : rawKey
  }

  const afterColon = trimSpaces(content.slice(colonIndex + 1))
  const bracketContent = content.slice(bracketStart + 1, bracketEnd)

  let parsedBracket                                        
  try {
    parsedBracket = parseBracketSegment(bracketContent, defaultDelimiter)
  }
  catch (error) {
    return { kind: 'invalid', reason: (error         ).message }
  }

  const { length, delimiter, keyed } = parsedBracket

  let fields                         
  if (braceStart !== -1 && braceStart < colonIndex) {
    const foundBraceEnd = findMatchingBrace(content, braceStart)
    if (foundBraceEnd !== -1 && foundBraceEnd < colonIndex) {
      const fieldsContent = content.slice(braceStart + 1, foundBraceEnd)

      const mismatchedDelimiter = findUnquotedMismatchedDelimiter(fieldsContent, delimiter)
      if (mismatchedDelimiter !== undefined) {
        return {
          kind: 'invalid',
          reason: `Header delimiter mismatch: bracket declares "${formatDelimiter(delimiter)}" but field list contains unquoted "${formatDelimiter(mismatchedDelimiter)}"`,
        }
      }

      try {
        fields = parseFieldEntries(fieldsContent, delimiter)
      }
      catch (error) {
        return { kind: 'invalid', reason: (error         ).message }
      }
    }
  }

  // Duplicate field names are strict-only – non-strict resolves them via LWW – so the
  // reason rides along on an otherwise-valid header, and the check below prefers it.
  const duplicateFieldName = fields ? findDuplicateFieldName(fields) : undefined
  const duplicateReason = duplicateFieldName
    ? `Duplicate field name "${duplicateFieldName}" in field list`
    : undefined

  if (keyed && !fields) {
    return { kind: 'invalid', reason: 'Keyed header requires a field list' }
  }

  // A fields-bearing header, keyed or not, carries no inline content;
  // decoding the values as an inline array would silently drop the fields.
  if (fields && afterColon) {
    return { kind: 'invalid', reason: duplicateReason ?? 'Unexpected content after fields-bearing header colon' }
  }

  return {
    kind: 'header',
    header: {
      key,
      length,
      delimiter,
      fields,
      keyed,
    },
    inlineValues: afterColon || undefined,
    strictError: duplicateReason,
  }
}

const BRACKET_LENGTH_PATTERN = /^(?:0|[1-9]\d*)$/

function parseBracketSegment(
  seg        ,
  defaultDelimiter           ,
)                                                           {
  let content = seg

  let delimiter = defaultDelimiter
  if (content.endsWith(TAB)) {
    delimiter = DELIMITERS.tab
    content = content.slice(0, -1)
  }
  else if (content.endsWith(PIPE)) {
    delimiter = DELIMITERS.pipe
    content = content.slice(0, -1)
  }

  // Only a colon between the length and the optional delimiter symbol marks a keyed
  // header; any other placement leaves a token that fails the length check below.
  let keyed = false
  if (content.endsWith(COLON)) {
    keyed = true
    content = content.slice(0, -1)
  }

  if (!BRACKET_LENGTH_PATTERN.test(content)) {
    throw new SyntaxError(`Invalid array length: "${seg}" (expected non-negative integer with no leading zeros)`)
  }

  return { length: Number.parseInt(content, 10), delimiter, keyed }
}

/**
 * Parses the content of a field list into field entries, recursively
 * descending into nested field groups (`field{sub1,sub2}`).
 *
 * @remarks
 * Throws on empty segments, empty names, unmatched braces, and content
 * after a nested group's closing brace; callers decide strict fallthrough.
 */
function parseFieldEntries(fieldsContent        , delimiter           )              {
  const entries = splitFieldEntries(fieldsContent, delimiter)

  return entries.map((entry) => {
    const trimmedEntry = trimSpaces(entry)
    if (!trimmedEntry) {
      throw new SyntaxError('Empty field name in field list')
    }

    const groupStart = findUnquotedChar(trimmedEntry, OPEN_BRACE)
    if (groupStart === -1) {
      return { name: parseStringLiteral(trimmedEntry) }
    }

    const namePart = trimSpaces(trimmedEntry.slice(0, groupStart))
    if (!namePart) {
      throw new SyntaxError('Missing field name before nested field group')
    }

    const groupEnd = findMatchingBrace(trimmedEntry, groupStart)
    if (groupEnd === -1) {
      throw new SyntaxError('Unmatched brace in field list')
    }
    if (groupEnd !== trimmedEntry.length - 1) {
      throw new SyntaxError('Unexpected content after nested field group')
    }

    const children = parseFieldEntries(trimmedEntry.slice(groupStart + 1, groupEnd), delimiter)
    return { name: parseStringLiteral(namePart), children }
  })
}

/**
 * Splits a field list on the active delimiter at brace depth zero,
 * respecting quoted names and escape sequences.
 */
function splitFieldEntries(content        , delimiter           )           {
  const entries           = []
  let entryBuffer = ''
  let inQuotes = false
  let braceDepth = 0
  let i = 0

  while (i < content.length) {
    const char = content[i] 

    if (char === BACKSLASH && i + 1 < content.length && inQuotes) {
      entryBuffer += char + content[i + 1]
      i += 2
      continue
    }

    if (char === DOUBLE_QUOTE) {
      inQuotes = !inQuotes
      entryBuffer += char
      i++
      continue
    }

    if (!inQuotes) {
      if (char === OPEN_BRACE) {
        braceDepth++
      }
      else if (char === CLOSE_BRACE) {
        braceDepth--
      }
      else if (char === delimiter && braceDepth === 0) {
        entries.push(entryBuffer)
        entryBuffer = ''
        i++
        continue
      }
    }

    entryBuffer += char
    i++
  }

  entries.push(entryBuffer)
  return entries
}

/**
 * Finds the index of the closing brace matching the opening brace at
 * `braceStart`, ignoring braces inside quoted names.
 */
function findMatchingBrace(content        , braceStart        )         {
  let inQuotes = false
  let braceDepth = 0
  let i = braceStart

  while (i < content.length) {
    const char = content[i]

    if (char === BACKSLASH && i + 1 < content.length && inQuotes) {
      i += 2
      continue
    }

    if (char === DOUBLE_QUOTE) {
      inQuotes = !inQuotes
      i++
      continue
    }

    if (!inQuotes) {
      if (char === OPEN_BRACE) {
        braceDepth++
      }
      else if (char === CLOSE_BRACE) {
        braceDepth--
        if (braceDepth === 0) {
          return i
        }
      }
    }

    i++
  }

  return -1
}

function findDuplicateFieldName(fields                      )                     {
  const seenNames = new Set        ()
  for (const field of fields) {
    if (seenNames.has(field.name)) {
      return field.name
    }
    seenNames.add(field.name)
    if (field.children) {
      const nestedDuplicate = findDuplicateFieldName(field.children)
      if (nestedDuplicate !== undefined) {
        return nestedDuplicate
      }
    }
  }
  return undefined
}

/**
 * Counts the leaf fields of a field list: the number of cells each row
 * carries, via a depth-first walk of nested field groups.
 */
function countLeafFields(fields                      )         {
  let leafCount = 0
  for (const field of fields) {
    leafCount += field.children ? countLeafFields(field.children) : 1
  }
  return leafCount
}

const DELIMITER_CANDIDATES                       = [',', '\t', '|']

function findUnquotedMismatchedDelimiter(content        , activeDelimiter           )                        {
  for (const candidate of DELIMITER_CANDIDATES) {
    if (candidate === activeDelimiter)
      continue
    if (findUnquotedChar(content, candidate) !== -1)
      return candidate
  }
}

function formatDelimiter(delimiter           )         {
  if (delimiter === '\t')
    return '\\t'
  return delimiter
}

// #endregion

// #region Delimited value parsing

/** Parses a delimited string into values, respecting quoted strings and escape sequences. */
function parseDelimitedValues(input        , delimiter           )           {
  const values           = []
  let valueBuffer = ''
  let inQuotes = false
  let i = 0

  while (i < input.length) {
    const char = input[i]

    if (char === BACKSLASH && i + 1 < input.length && inQuotes) {
      valueBuffer += char + input[i + 1]
      i += 2
      continue
    }

    if (char === DOUBLE_QUOTE) {
      inQuotes = !inQuotes
      valueBuffer += char
      i++
      continue
    }

    if (char === delimiter && !inQuotes) {
      values.push(trimSpaces(valueBuffer))
      valueBuffer = ''
      i++
      continue
    }

    valueBuffer += char
    i++
  }

  if (valueBuffer || values.length > 0) {
    values.push(trimSpaces(valueBuffer))
  }

  return values
}

function mapRowValuesToPrimitives(values          )                  {
  return values.map(v => parsePrimitiveToken(v))
}

// #endregion

// #region Primitive and key parsing

function parsePrimitiveToken(token        )                {
  const trimmedToken = trimSpaces(token)

  if (!trimmedToken) {
    return ''
  }

  if (trimmedToken.startsWith(DOUBLE_QUOTE)) {
    return parseStringLiteral(trimmedToken)
  }

  if (isBooleanOrNullLiteral(trimmedToken)) {
    if (trimmedToken === TRUE_LITERAL)
      return true
    if (trimmedToken === FALSE_LITERAL)
      return false
    if (trimmedToken === NULL_LITERAL)
      return null
  }

  if (isNumericLiteral(trimmedToken)) {
    const parsedNumber = Number.parseFloat(trimmedToken)
    return Object.is(parsedNumber, -0) ? 0 : parsedNumber
  }

  return trimmedToken
}

function parseStringLiteral(token        )         {
  const trimmedToken = trimSpaces(token)

  if (trimmedToken.startsWith(DOUBLE_QUOTE)) {
    const closingQuoteIndex = findClosingQuote(trimmedToken, 0)

    if (closingQuoteIndex === -1) {
      throw new SyntaxError('Unterminated string: missing closing quote')
    }

    if (closingQuoteIndex !== trimmedToken.length - 1) {
      throw new SyntaxError('Unexpected characters after closing quote')
    }

    const content = trimmedToken.slice(1, closingQuoteIndex)
    return unescapeString(content)
  }

  return trimmedToken
}

function parseUnquotedKey(content        , start        )                               {
  // A raw scan would cut `a "b:c" d: 1` at the quoted colon and split the key in two.
  const colonIndex = findUnquotedChar(content, COLON, start)

  if (colonIndex === -1) {
    throw new SyntaxError('Missing colon after key')
  }

  return { key: trimSpaces(content.slice(start, colonIndex)), end: colonIndex + 1 }
}

function parseQuotedKey(content        , start        )                               {
  const closingQuoteIndex = findClosingQuote(content, start)

  if (closingQuoteIndex === -1) {
    throw new SyntaxError('Unterminated quoted key')
  }

  const keyContent = content.slice(start + 1, closingQuoteIndex)
  const key = unescapeString(keyContent)
  let parsePosition = closingQuoteIndex + 1

  if (parsePosition >= content.length || content[parsePosition] !== COLON) {
    throw new SyntaxError('Missing colon after key')
  }
  parsePosition++

  return { key, end: parsePosition }
}

function parseKeyToken(content        , start        )                               {
  return content[start] === DOUBLE_QUOTE
    ? parseQuotedKey(content, start)
    : parseUnquotedKey(content, start)
}

// #endregion

// #region Array content detection helpers

function isArrayHeaderContent(content        )          {
  return content.trim().startsWith(OPEN_BRACKET) && findUnquotedChar(content, COLON) !== -1
}

function isKeyValueContent(content        )          {
  return findUnquotedChar(content, COLON) !== -1
}

// #endregion

exports.parseArrayHeaderLine = parseArrayHeaderLine;
exports.parseBracketSegment = parseBracketSegment;
exports.parseFieldEntries = parseFieldEntries;
exports.findMatchingBrace = findMatchingBrace;
exports.countLeafFields = countLeafFields;
exports.parseDelimitedValues = parseDelimitedValues;
exports.mapRowValuesToPrimitives = mapRowValuesToPrimitives;
exports.parsePrimitiveToken = parsePrimitiveToken;
exports.parseStringLiteral = parseStringLiteral;
exports.parseUnquotedKey = parseUnquotedKey;
exports.parseQuotedKey = parseQuotedKey;
exports.parseKeyToken = parseKeyToken;
exports.isArrayHeaderContent = isArrayHeaderContent;
exports.isKeyValueContent = isKeyValueContent;
};
__defs['decode/scanner.ts'] = function(exports, module){
                                                                   
const { BYTE_ORDER_MARK, CARRIAGE_RETURN, COMMENT_MARKER, SPACE, TAB } = __require('constants.ts');
const { ToonDecodeError } = __require('decode/errors.ts');

const LEADING_WHITESPACE_PATTERN = /^[ \t]*/

// #region Scan state

                                     
                    
                             
 

function createScanState()                     {
  return {
    lineNumber: 0,
    blankLines: [],
  }
}

// #endregion

// #region Line parsing

function parseLineIncremental(
  raw        ,
  state                    ,
  indentSize        ,
  strict         ,
)                         {
  state.lineNumber++
  const lineNumber = state.lineNumber

  if (lineNumber === 1 && raw[0] === BYTE_ORDER_MARK) {
    raw = raw.slice(1)
  }

  // A trailing carriage return belongs to the CRLF terminator, not to the content.
  if (raw[raw.length - 1] === CARRIAGE_RETURN) {
    raw = raw.slice(0, -1)
  }

  const leadingWhitespace = LEADING_WHITESPACE_PATTERN.exec(raw) [0]
  const firstTabIndex = leadingWhitespace.indexOf(TAB)

  // Strict rejects tab indentation below, so only the spaces before the first tab are indentation there.
  const indent = strict && firstTabIndex !== -1 ? firstTabIndex : leadingWhitespace.length
  // Non-strict input may indent with tabs, and each tab counts as one depth level.
  const tabIndent = strict || firstTabIndex === -1 ? 0 : leadingWhitespace.split(TAB).length - 1

  // Without this, `- ` would be an item carrying an empty token instead of the bare list-item marker.
  const content = trimTrailingSpaces(raw.slice(indent))

  // Only spaces may precede the marker, so a tab in the indentation rules the line out.
  // Comment lines vanish before blank-line tracking and strict validation, so they
  // never count as rows, items, entries, or blank lines.
  if (firstTabIndex === -1 && content[0] === COMMENT_MARKER) {
    return undefined
  }

  const depth = computeDepthFromIndent(indent - tabIndent, indentSize) + tabIndent

  if (!content) {
    state.blankLines.push({ lineNumber, indent, depth })
    return undefined
  }

  if (strict) {
    if (firstTabIndex !== -1) {
      throw new ToonDecodeError(
        'Tabs are not allowed in indentation in strict mode',
        { line: lineNumber, source: raw },
      )
    }

    if (indent > 0 && indent % indentSize !== 0) {
      throw new ToonDecodeError(
        `Indentation must be exact multiple of ${indentSize}, but found ${indent} spaces`,
        { line: lineNumber, source: raw },
      )
    }
  }

  return { raw, indent, content, depth, lineNumber }
}

function computeDepthFromIndent(indentSpaces        , indentSize        )        {
  return Math.floor(indentSpaces / indentSize)
}

function trimTrailingSpaces(value        )         {
  let end = value.length
  while (end > 0 && value[end - 1] === SPACE) {
    end--
  }
  return end === value.length ? value : value.slice(0, end)
}

// #endregion

exports.createScanState = createScanState;
exports.parseLineIncremental = parseLineIncremental;
};
__defs['decode/validation.ts'] = function(exports, module){
                                                                                               
const { COLON, LIST_ITEM_PREFIX } = __require('constants.ts');
const { findUnquotedChar } = __require('shared/string-utils.ts');
const { ToonDecodeError } = __require('decode/errors.ts');

// #region Count and structure validation

function assertExpectedCount(
  actual        ,
  expected        ,
  itemType        ,
  options                     ,
  line            ,
)       {
  if (options.strict && actual !== expected) {
    throw new ToonDecodeError(
      `Expected ${expected} ${itemType}, but got ${actual}`,
      { line: line.lineNumber, source: line.raw },
    )
  }
}

function validateNoExtraListItems(
  nextLine                        ,
  itemDepth       ,
  expectedCount        ,
)       {
  if (nextLine?.depth === itemDepth && nextLine.content.startsWith(LIST_ITEM_PREFIX)) {
    throw new ToonDecodeError(
      `Expected ${expectedCount} list-form items, but found more`,
      { line: nextLine.lineNumber, source: nextLine.raw },
    )
  }
}

function validateNoExtraTabularRows(
  nextLine                        ,
  rowDepth       ,
  header                 ,
)       {
  if (
    nextLine?.depth === rowDepth
    && !nextLine.content.startsWith(LIST_ITEM_PREFIX)
    && isDataRow(nextLine.content, header.delimiter)
  ) {
    throw new ToonDecodeError(
      `Expected ${header.length} tabular rows, but found more`,
      { line: nextLine.lineNumber, source: nextLine.raw },
    )
  }
}

function validateNoBlankLinesInRange(
  startLine        ,
  endLine        ,
  blankLines                 ,
  strict         ,
  context        ,
)       {
  if (!strict)
    return

  const firstBlank = blankLines.find(
    blank => blank.lineNumber > startLine && blank.lineNumber < endLine,
  )

  if (firstBlank) {
    throw new ToonDecodeError(
      `Blank lines inside ${context} are not allowed in strict mode`,
      { line: firstBlank.lineNumber },
    )
  }
}

// #endregion

// #region Row classification helpers

/** Checks if a line is a data row (vs a key-value pair) in a tabular array. */
function isDataRow(content        , delimiter           )          {
  const colonPos = findUnquotedChar(content, COLON)
  const delimiterPos = findUnquotedChar(content, delimiter)

  if (colonPos === -1) {
    return true
  }

  if (delimiterPos !== -1 && delimiterPos < colonPos) {
    return true
  }

  return false
}

// #endregion

exports.assertExpectedCount = assertExpectedCount;
exports.validateNoExtraListItems = validateNoExtraListItems;
exports.validateNoExtraTabularRows = validateNoExtraTabularRows;
exports.validateNoBlankLinesInRange = validateNoBlankLinesInRange;
exports.isDataRow = isDataRow;
};
__defs['encode/encoders.ts'] = function(exports, module){
                                                                                                            
                                                         
const { LIST_ITEM_MARKER, LIST_ITEM_PREFIX } = __require('constants.ts');
const { isArrayOfArrays, isArrayOfObjects, isArrayOfPrimitives, isEmptyObject, isEncodablePrimitive, isJsonArray, isJsonObject } = __require('encode/normalize.ts');
const { encodeAndJoinPrimitives, encodeKey, encodePrimitive, formatHeader } = __require('encode/primitives.ts');
const { collectRowLeaves, extractKeyedTabularFields, extractTabularFields } = __require('encode/tabular.ts');

// #region Encode normalized JsonValue

function* encodeJsonValue(value           , options                       , depth       )                    {
  if (isEncodablePrimitive(value)) {
    const encodedPrimitive = encodePrimitive(value, options.delimiter)

    if (encodedPrimitive !== '')
      yield encodedPrimitive

    return
  }

  if (isJsonArray(value)) {
    yield* encodeArrayLines(undefined, value, depth, options)
  }
  else if (isJsonObject(value)) {
    // A keyed-eligible root object uses the keyless keyed header.
    const keyedFields = extractKeyedTabularFields(value)
    if (keyedFields) {
      yield* encodeKeyedObjectLines(undefined, value, keyedFields, depth, options)
      return
    }

    yield* encodeObjectLines(value, depth, options)
  }
}

// #endregion

// #region Object encoding

function* encodeObjectLines(
  value            ,
  depth       ,
  options                       ,
)                    {
  for (const [key, val] of Object.entries(value)) {
    yield* encodeKeyValuePairLines(key, val, depth, options)
  }
}

function* encodeKeyValuePairLines(
  key        ,
  value           ,
  depth       ,
  options                       ,
)                    {
  const encodedKey = encodeKey(key)

  if (isEncodablePrimitive(value)) {
    yield indentedLine(depth, `${encodedKey}: ${encodePrimitive(value, options.delimiter)}`, options.indentSize)
  }
  else if (isJsonArray(value)) {
    yield* encodeArrayLines(key, value, depth, options)
  }
  else if (isJsonObject(value)) {
    const keyedFields = extractKeyedTabularFields(value)
    if (keyedFields) {
      yield* encodeKeyedObjectLines(key, value, keyedFields, depth, options)
      return
    }

    yield indentedLine(depth, `${encodedKey}:`, options.indentSize)
    if (!isEmptyObject(value)) {
      yield* encodeObjectLines(value, depth + 1, options)
    }
  }
}

// #endregion

// #region Keyed tabular objects

function* encodeKeyedObjectLines(
  key                    ,
  value            ,
  fields                      ,
  depth       ,
  options                       ,
)                    {
  const entries = Object.entries(value)
  const header = formatHeader(entries.length, { key, fields, delimiter: options.delimiter, keyed: true })
  yield indentedLine(depth, header, options.indentSize)
  yield* encodeKeyedEntryRowsLines(entries, fields, depth + 1, options)
}

function* encodeKeyedEntryRowsLines(
  entries                                ,
  fields                      ,
  depth       ,
  options                       ,
)                    {
  for (const [entryKey, entryValue] of entries) {
    const leaves = collectRowLeaves(entryValue              , fields)
    yield indentedLine(depth, `${encodeKey(entryKey)}: ${encodeAndJoinPrimitives(leaves, options.delimiter)}`, options.indentSize)
  }
}

// #endregion

// #region Array encoding

function* encodeArrayLines(
  key                    ,
  value           ,
  depth       ,
  options                       ,
)                    {
  if (value.length === 0) {
    const line = key != null ? `${encodeKey(key)}: []` : '[]'
    yield indentedLine(depth, line, options.indentSize)
    return
  }

  if (isArrayOfPrimitives(value)) {
    const arrayLine = encodeInlineArrayLine(value, options.delimiter, key)
    yield indentedLine(depth, arrayLine, options.indentSize)
    return
  }

  if (isArrayOfArrays(value)) {
    const allPrimitiveArrays = value.every(arr => isArrayOfPrimitives(arr))
    if (allPrimitiveArrays) {
      yield* encodeArrayOfArraysAsListItemsLines(key, value, depth, options)
      return
    }
  }

  if (isArrayOfObjects(value)) {
    const fields = extractTabularFields(value)
    if (fields) {
      yield* encodeArrayOfObjectsAsTabularLines(key, value, fields, depth, options)
    }
    else {
      yield* encodeMixedArrayAsListItemsLines(key, value, depth, options)
    }
    return
  }

  yield* encodeMixedArrayAsListItemsLines(key, value, depth, options)
}

// #endregion

// #region Array of arrays (list form)

function* encodeArrayOfArraysAsListItemsLines(
  prefix                    ,
  values                      ,
  depth       ,
  options                       ,
)                    {
  const header = formatHeader(values.length, { key: prefix, delimiter: options.delimiter })
  yield indentedLine(depth, header, options.indentSize)

  for (const arr of values) {
    if (isArrayOfPrimitives(arr)) {
      const arrayLine = encodeInlineArrayLine(arr, options.delimiter)
      yield indentedListItem(depth + 1, arrayLine, options.indentSize)
    }
  }
}

function encodeInlineArrayLine(values                               , delimiter        , prefix         )         {
  const header = formatHeader(values.length, { key: prefix, delimiter })
  const joinedValue = encodeAndJoinPrimitives(values, delimiter)

  if (values.length === 0)
    return header

  return `${header} ${joinedValue}`
}

// #endregion

// #region Array of objects (tabular form)

function* encodeArrayOfObjectsAsTabularLines(
  prefix                    ,
  rows                       ,
  fields                      ,
  depth       ,
  options                       ,
)                    {
  const header = formatHeader(rows.length, { key: prefix, fields, delimiter: options.delimiter })
  yield indentedLine(depth, header, options.indentSize)

  yield* writeTabularRowsLines(rows, fields, depth + 1, options)
}

function* writeTabularRowsLines(
  rows                       ,
  fields                      ,
  depth       ,
  options                       ,
)                    {
  for (const row of rows) {
    const leaves = collectRowLeaves(row, fields)
    yield indentedLine(depth, encodeAndJoinPrimitives(leaves, options.delimiter), options.indentSize)
  }
}

// #endregion

// #region Array of objects (list form)

function* encodeMixedArrayAsListItemsLines(
  prefix                    ,
  items                      ,
  depth       ,
  options                       ,
)                    {
  const header = formatHeader(items.length, { key: prefix, delimiter: options.delimiter })
  yield indentedLine(depth, header, options.indentSize)

  for (const item of items) {
    yield* encodeListItemValueLines(item, depth + 1, options)
  }
}

function* encodeObjectAsListItemLines(
  obj            ,
  depth       ,
  options                       ,
)                    {
  if (isEmptyObject(obj)) {
    yield indentedLine(depth, LIST_ITEM_MARKER, options.indentSize)
    return
  }

  const entries = Object.entries(obj)
  const [firstKey, firstValue] = entries[0] 
  const restEntries = entries.slice(1)

  if (isJsonArray(firstValue) && isArrayOfObjects(firstValue)) {
    const fields = extractTabularFields(firstValue)
    if (fields) {
      const header = formatHeader(firstValue.length, { key: firstKey, fields, delimiter: options.delimiter })
      yield indentedListItem(depth, header, options.indentSize)
      yield* writeTabularRowsLines(firstValue, fields, depth + 2, options)

      if (restEntries.length > 0) {
        const restObj             = Object.fromEntries(restEntries)
        yield* encodeObjectLines(restObj, depth + 1, options)
      }
      return
    }
  }

  // Keyed first field: header on the hyphen line, entry rows at depth +2, siblings at +1.
  if (isJsonObject(firstValue)) {
    const keyedFields = extractKeyedTabularFields(firstValue)
    if (keyedFields) {
      const keyedEntries = Object.entries(firstValue)
      const header = formatHeader(keyedEntries.length, { key: firstKey, fields: keyedFields, delimiter: options.delimiter, keyed: true })
      yield indentedListItem(depth, header, options.indentSize)
      yield* encodeKeyedEntryRowsLines(keyedEntries, keyedFields, depth + 2, options)

      if (restEntries.length > 0) {
        const restObj             = Object.fromEntries(restEntries)
        yield* encodeObjectLines(restObj, depth + 1, options)
      }
      return
    }
  }

  const encodedKey = encodeKey(firstKey)

  if (isEncodablePrimitive(firstValue)) {
    const encodedValue = encodePrimitive(firstValue, options.delimiter)
    yield indentedListItem(depth, `${encodedKey}: ${encodedValue}`, options.indentSize)
  }
  else if (isJsonArray(firstValue)) {
    if (firstValue.length === 0) {
      yield indentedListItem(depth, `${encodedKey}: []`, options.indentSize)
    }
    else if (isArrayOfPrimitives(firstValue)) {
      const arrayLine = encodeInlineArrayLine(firstValue, options.delimiter)
      yield indentedListItem(depth, `${encodedKey}${arrayLine}`, options.indentSize)
    }
    else {
      // Non-inline array items sit at depth + 2, below the hyphen line.
      const header = formatHeader(firstValue.length, { delimiter: options.delimiter })
      yield indentedListItem(depth, `${encodedKey}${header}`, options.indentSize)

      for (const item of firstValue) {
        yield* encodeListItemValueLines(item, depth + 2, options)
      }
    }
  }
  else if (isJsonObject(firstValue)) {
    yield indentedListItem(depth, `${encodedKey}:`, options.indentSize)
    if (!isEmptyObject(firstValue)) {
      yield* encodeObjectLines(firstValue, depth + 2, options)
    }
  }

  if (restEntries.length > 0) {
    const restObj             = Object.fromEntries(restEntries)
    yield* encodeObjectLines(restObj, depth + 1, options)
  }
}

// #endregion

// #region List item encoding helpers

function* encodeListItemValueLines(
  value           ,
  depth       ,
  options                       ,
)                    {
  if (isEncodablePrimitive(value)) {
    yield indentedListItem(depth, encodePrimitive(value, options.delimiter), options.indentSize)
  }
  else if (isJsonArray(value)) {
    if (isArrayOfPrimitives(value)) {
      const arrayLine = encodeInlineArrayLine(value, options.delimiter)
      yield indentedListItem(depth, arrayLine, options.indentSize)
    }
    else {
      const header = formatHeader(value.length, { delimiter: options.delimiter })
      yield indentedListItem(depth, header, options.indentSize)
      for (const item of value) {
        yield* encodeListItemValueLines(item, depth + 1, options)
      }
    }
  }
  else if (isJsonObject(value)) {
    yield* encodeObjectAsListItemLines(value, depth, options)
  }
}

// #endregion

// #region Indentation helpers

function indentedLine(depth       , content        , indentSize        )         {
  const indentation = ' '.repeat(indentSize * depth)
  return indentation + content
}

function indentedListItem(depth       , content        , indentSize        )         {
  return indentedLine(depth, LIST_ITEM_PREFIX + content, indentSize)
}

// #endregion

exports.encodeJsonValue = encodeJsonValue;
};
__defs['encode/normalize.ts'] = function(exports, module){
                                                                                  
                                                         
const { setOwnProperty } = __require('shared/object-utils.ts');
const { isRawString } = __require('encode/raw-string.ts');

const SURROGATE_PATTERN = /[\uD800-\uDFFF]/

// #region Normalization (unknown → JsonValue)

function normalizeValue(value         )            {
  if (value === null) {
    return null
  }

  // `RawString` markers pass through untouched, treated as primitives and never as objects.
  if (isRawString(value)) {
    return value                        
  }

  // A host `toJSON` hook takes precedence over the default host-type mappings below.
  if (
    typeof value === 'object'
    && value !== null
    && 'toJSON' in value
    && typeof value.toJSON === 'function'
  ) {
    const next = value.toJSON()
    // Avoid infinite recursion when `toJSON` returns the same object.
    if (next !== value) {
      return normalizeValue(next)
    }
  }

  if (typeof value === 'string') {
    assertNoLoneSurrogate(value, 'string value')
    return value
  }

  if (typeof value === 'boolean') {
    return value
  }

  if (typeof value === 'number') {
    if (Object.is(value, -0)) {
      return 0
    }
    if (!Number.isFinite(value)) {
      return null
    }
    return value
  }

  if (typeof value === 'bigint') {
    if (value >= Number.MIN_SAFE_INTEGER && value <= Number.MAX_SAFE_INTEGER) {
      return Number(value)
    }
    return value.toString()
  }

  if (value instanceof Date) {
    return value.toISOString()
  }

  if (Array.isArray(value)) {
    return value.map(normalizeValue)
  }

  if (value instanceof Set) {
    return Array.from(value).map(normalizeValue)
  }

  if (value instanceof Map) {
    return Object.fromEntries(
      Array.from(value, ([k, v]) => [String(k), normalizeValue(v)]),
    )
  }

  if (isPlainObject(value)) {
    const encodedValues                            = {}

    for (const key in value) {
      if (Object.hasOwn(value, key)) {
        assertNoLoneSurrogate(key, 'object key')
        setOwnProperty(encodedValues, key, normalizeValue(value[key]))
      }
    }

    return encodedValues
  }

  return null
}

// A lone surrogate has no UTF-8 form, so emitting it would silently substitute U+FFFD and break round-tripping.
function assertNoLoneSurrogate(value        , context        )       {
  if (!SURROGATE_PATTERN.test(value)) {
    return
  }

  for (let index = 0; index < value.length; index++) {
    const code = value.charCodeAt(index)
    if (code < 0xD800 || code > 0xDFFF) {
      continue
    }

    const isHighSurrogate = code <= 0xDBFF
    const next = value.charCodeAt(index + 1)
    if (isHighSurrogate && next >= 0xDC00 && next <= 0xDFFF) {
      index++
      continue
    }

    throw new TypeError(
      `Cannot encode ${context} containing an unpaired surrogate U+${code.toString(16).toUpperCase()} at index ${index}`,
    )
  }
}

// #endregion

// #region Type guards

function isJsonPrimitive(value         )                         {
  return (
    value === null
    || typeof value === 'string'
    || typeof value === 'number'
    || typeof value === 'boolean'
  )
}

function isEncodablePrimitive(value         )                              {
  return isJsonPrimitive(value) || isRawString(value)
}

function isJsonArray(value         )                     {
  return Array.isArray(value)
}

function isJsonObject(value         )                      {
  return value !== null && typeof value === 'object' && !Array.isArray(value) && !isRawString(value)
}

function isEmptyObject(value            )          {
  return Object.keys(value).length === 0
}

function isPlainObject(value         )                                   {
  if (value === null || typeof value !== 'object') {
    return false
  }

  const prototype = Object.getPrototypeOf(value)
  return prototype === null || prototype === Object.prototype
}

// #endregion

// #region Array type detection

function isArrayOfPrimitives(value                                           )                                         {
  return value.length === 0 || value.every(item => isEncodablePrimitive(item))
}

function isArrayOfArrays(value           )                                {
  return value.length === 0 || value.every(item => isJsonArray(item))
}

function isArrayOfObjects(value           )                                 {
  return value.length === 0 || value.every(item => isJsonObject(item))
}

// #endregion

exports.normalizeValue = normalizeValue;
exports.isJsonPrimitive = isJsonPrimitive;
exports.isEncodablePrimitive = isEncodablePrimitive;
exports.isJsonArray = isJsonArray;
exports.isJsonObject = isJsonObject;
exports.isEmptyObject = isEmptyObject;
exports.isPlainObject = isPlainObject;
exports.isArrayOfPrimitives = isArrayOfPrimitives;
exports.isArrayOfArrays = isArrayOfArrays;
exports.isArrayOfObjects = isArrayOfObjects;
};
__defs['encode/primitives.ts'] = function(exports, module){
                                            
                                                         
const { COMMA, DEFAULT_DELIMITER, DOUBLE_QUOTE, NULL_LITERAL } = __require('constants.ts');
const { escapeString } = __require('shared/string-utils.ts');
const { isSafeUnquoted, isValidUnquotedKey } = __require('shared/validation.ts');
const { isRawString } = __require('encode/raw-string.ts');

// #region Primitive encoding

function encodePrimitive(value                    , delimiter         )         {
  if (isRawString(value)) {
    return value.value
  }

  if (value === null) {
    return NULL_LITERAL
  }

  if (typeof value === 'boolean') {
    return String(value)
  }

  if (typeof value === 'number') {
    return String(value)
  }

  return encodeStringLiteral(value, delimiter)
}

function encodeStringLiteral(value        , delimiter         = DEFAULT_DELIMITER)         {
  if (isSafeUnquoted(value, delimiter)) {
    return value
  }

  return `${DOUBLE_QUOTE}${escapeString(value)}${DOUBLE_QUOTE}`
}

// #endregion

// #region Key encoding

function encodeKey(key        )         {
  if (isValidUnquotedKey(key)) {
    return key
  }

  return `${DOUBLE_QUOTE}${escapeString(key)}${DOUBLE_QUOTE}`
}

// #endregion

// #region Value joining

function encodeAndJoinPrimitives(values                               , delimiter         = DEFAULT_DELIMITER)         {
  return values.map(v => encodePrimitive(v, delimiter)).join(delimiter)
}

// #endregion

// #region Header formatters

function formatHeader(
  length        ,
  options    
                
                                 
                      
                                                                        
                   
   ,
)         {
  const key = options?.key
  const fields = options?.fields
  const delimiter = options?.delimiter ?? COMMA

  let header = ''

  if (key != null) {
    header += encodeKey(key)
  }

  header += `[${length}${options?.keyed ? ':' : ''}${delimiter !== DEFAULT_DELIMITER ? delimiter : ''}]`

  if (fields) {
    header += `{${formatFieldSegment(fields, delimiter)}}`
  }

  header += ':'

  return header
}

function formatFieldSegment(fields                      , delimiter        )         {
  return fields
    .map(field => encodeKey(field.name) + (field.children ? `{${formatFieldSegment(field.children, delimiter)}}` : ''))
    .join(delimiter)
}

// #endregion

exports.encodePrimitive = encodePrimitive;
exports.encodeStringLiteral = encodeStringLiteral;
exports.encodeKey = encodeKey;
exports.encodeAndJoinPrimitives = encodeAndJoinPrimitives;
exports.formatHeader = formatHeader;
};
__defs['encode/raw-string.ts'] = function(exports, module){
                                                
const { BYTE_ORDER_MARK, COMMENT_MARKER } = __require('constants.ts');

// Decoders silently strip a line whose first non-space character is the comment marker,
// and they remove a leading byte-order mark before making that test.
const COMMENT_LINE_PATTERN = new RegExp(`(?:^${BYTE_ORDER_MARK}?|\\n) *${COMMENT_MARKER}`)

/**
 * Pre-formatted string that the encoder emits verbatim at a primitive value
 * position, bypassing quoting, escaping, and number/keyword detection.
 *
 * Returned from a replacer for an object or array value, it is ignored and
 * the container is encoded normally.
 */
class RawString {
           value        

  constructor(value        ) {
    if (COMMENT_LINE_PATTERN.test(value)) {
      throw new TypeError(`Raw string must not contain a line starting with "${COMMENT_MARKER}": ${JSON.stringify(value)}`)
    }
    this.value = value
  }
}

/** Values the encoder can emit at a primitive position. */
                                                          

/**
 * Wraps a pre-formatted string for verbatim emission, typically returned from
 * an encode `replacer`. Compose with `escapeString` to control quoting yourself.
 *
 * @param value The exact text to emit at the value position
 * @returns A `RawString` marker honored at primitive value positions
 *
 * @example
 * ```ts
 * encode({ name: 'Ada', age: 30 }, {
 *   replacer: (key, value) => rawString(`"${escapeString(String(value))}"`)
 * })
 * // name: "Ada"
 * // age: "30"
 * ```
 */
function rawString(value        )            {
  return new RawString(value)
}

function isRawString(value         )                     {
  return value instanceof RawString
}

exports.RawString = RawString;
exports.rawString = rawString;
exports.isRawString = isRawString;
};
__defs['encode/replacer.ts'] = function(exports, module){
                                                                                   
const { setOwnProperty } = __require('shared/object-utils.ts');
const { isEncodablePrimitive, isJsonArray, isJsonObject, normalizeValue } = __require('encode/normalize.ts');
const { isRawString } = __require('encode/raw-string.ts');

/**
 * Applies a replacer function to a `JsonValue` and all its descendants.
 *
 * The replacer is called for the root (key='', path=[]), every object property
 * (key = property name), and every array element (key = string index).
 */
function applyReplacer(root           , replacer                )            {
  const replacedRoot = replacer('', root, [])

  // At the root, `undefined` means "no change", never omission.
  if (replacedRoot === undefined) {
    return transformChildren(root, replacer, [])
  }

  return transformReplaced(root, replacedRoot, replacer, [])
}

/**
 * Resolves a replacer's (non-`undefined`) return value at a single position.
 *
 * A `RawString` only stands in for a primitive: returned for an object or
 * array value, it is ignored and the original container is traversed normally.
 */
function transformReplaced(
  original           ,
  replaced         ,
  replacer                ,
  path                              ,
)            {
  if (isRawString(replaced) && !isEncodablePrimitive(original)) {
    return transformChildren(original, replacer, path)
  }

  // Normalize in case the replacer returned a non-`JsonValue`.
  return transformChildren(normalizeValue(replaced), replacer, path)
}

function transformChildren(
  value           ,
  replacer                ,
  path                              ,
)            {
  if (isJsonObject(value)) {
    return transformObject(value, replacer, path)
  }

  if (isJsonArray(value)) {
    return transformArray(value, replacer, path)
  }

  return value
}

function transformObject(
  obj            ,
  replacer                ,
  path                              ,
)             {
  const result                            = {}

  for (const [key, value] of Object.entries(obj)) {
    const childPath = [...path, key]
    const replacedValue = replacer(key, value, childPath)

    if (replacedValue === undefined) {
      continue
    }

    setOwnProperty(result, key, transformReplaced(value, replacedValue, replacer, childPath))
  }

  return result
}

function transformArray(
  arr           ,
  replacer                ,
  path                              ,
)            {
  const result              = []

  for (let i = 0; i < arr.length; i++) {
    const value = arr[i] 
    // String index (`'0'`, `'1'`, etc.) matches `JSON.stringify` behavior.
    const childPath = [...path, i]
    const replacedValue = replacer(String(i), value, childPath)

    if (replacedValue === undefined) {
      continue
    }

    result.push(transformReplaced(value, replacedValue, replacer, childPath))
  }

  return result
}

exports.applyReplacer = applyReplacer;
};
__defs['encode/tabular.ts'] = function(exports, module){
                                                                   
                                                         
const { isEmptyObject, isEncodablePrimitive, isJsonObject } = __require('encode/normalize.ts');

/** Classifies rows into a tabular field list, or undefined when they are not uniformly tabular. */
function extractTabularFields(rows                       )                          {
  if (rows.length === 0)
    return

  const firstKeys = Object.keys(rows[0] )
  if (firstKeys.length === 0)
    return

  // All objects must have the same set of keys (order per object may vary).
  for (const row of rows) {
    if (Object.keys(row).length !== firstKeys.length) {
      return
    }

    for (const key of firstKeys) {
      if (!Object.hasOwn(row, key)) {
        return
      }
    }
  }

  const fieldNodes              = []
  for (const key of firstKeys) {
    const fieldNode = classifyColumn(key, rows.map(row => row[key] ))
    if (!fieldNode) {
      return
    }
    fieldNodes.push(fieldNode)
  }

  return fieldNodes
}

/** Classifies an object's values as a keyed tabular field list (>=2 uniform non-empty object entries), or undefined. */
function extractKeyedTabularFields(value            )                          {
  const entryValues = Object.values(value)

  if (entryValues.length < 2) {
    return
  }

  if (!entryValues.every(entryValue => isJsonObject(entryValue) && !isEmptyObject(entryValue))) {
    return
  }

  return extractTabularFields(entryValues                )
}

/** Reads one row's leaf cells in the field order `extractTabularFields` produced. */
function collectRowLeaves(row            , fields                      )                       {
  const leaves                       = []
  collectLeafValues(row, fields, leaves)
  return leaves
}

function classifyColumn(name        , values                      )                        {
  // Uniform-primitive column: a bare leaf field.
  if (values.every(value => isEncodablePrimitive(value))) {
    return { name }
  }

  // Nested-uniform column: non-empty objects sharing one key set, classified recursively.
  if (!values.every(value => isJsonObject(value) && !isEmptyObject(value))) {
    return
  }

  const children = extractTabularFields(values                )
  if (!children) {
    return
  }

  return { name, children }
}

function collectLeafValues(row            , fields                      , leaves                      )       {
  for (const field of fields) {
    const value = row[field.name]
    if (field.children) {
      collectLeafValues(value              , field.children, leaves)
    }
    else {
      leaves.push(value                      )
    }
  }
}

exports.extractTabularFields = extractTabularFields;
exports.extractKeyedTabularFields = extractKeyedTabularFields;
exports.collectRowLeaves = collectRowLeaves;
};
__defs['index.ts'] = function(exports, module){
                                                                                                                                                             
const { DEFAULT_DELIMITER } = __require('constants.ts');
const { decodeStream: decodeStreamCore, decodeStreamSync: decodeStreamSyncCore } = __require('decode/decoders.ts');
const { buildValueFromEvents } = __require('decode/event-builder.ts');
const { encodeJsonValue } = __require('encode/encoders.ts');
const { normalizeValue } = __require('encode/normalize.ts');
const { applyReplacer } = __require('encode/replacer.ts');
const { assertValidDelimiter } = __require('shared/validation.ts');

exports.DEFAULT_DELIMITER = __require('constants.ts').DEFAULT_DELIMITER;
exports.DELIMITERS = __require('constants.ts').DELIMITERS;
exports.ToonDecodeError = __require('decode/errors.ts').ToonDecodeError;
exports.rawString = __require('encode/raw-string.ts').rawString;
                                                       
exports.escapeString = __require('shared/string-utils.ts').escapeString;
             
                
                      
            
               
                
                 
            
             
                
                  
            
                        
                        
                   

/**
 * Encodes a JavaScript value into TOON format string.
 *
 * @param input Any JavaScript value (objects, arrays, primitives)
 * @param options Optional encoding configuration
 * @returns TOON formatted string
 *
 * @example
 * ```ts
 * encode({ name: 'Ada', age: 30 })
 * // name: Ada
 * // age: 30
 *
 * encode({ users: [{ id: 1 }, { id: 2 }] })
 * // users[2]{id}:
 * //   1
 * //   2
 *
 * encode({ tags: [] })
 * // tags: []
 *
 * encode(data, { indentSize: 4 })
 * ```
 */
function encode(input         , options                )         {
  return Array.from(encodeLines(input, options)).join('\n')
}

/**
 * Decodes a TOON format string into a JavaScript value.
 *
 * @param input TOON formatted string
 * @param options Optional decoding configuration
 * @returns Parsed JavaScript value (object, array, or primitive)
 *
 * @example
 * ```ts
 * decode('name: Ada\nage: 30')
 * // { name: 'Ada', age: 30 }
 *
 * decode('users[2]:\n  - id: 1\n  - id: 2')
 * // { users: [{ id: 1 }, { id: 2 }] }
 *
 * decode('tags: []')
 * // { tags: [] }
 *
 * decode(toonString, { strict: false })
 * ```
 */
function decode(input        , options                )            {
  const lines = input.split('\n')
  return decodeFromLines(lines, options)
}

/**
 * Encodes a JavaScript value into TOON format as a sequence of lines.
 *
 * This function yields TOON lines one at a time without building the full string,
 * making it suitable for streaming large outputs to files, HTTP responses, or process stdout.
 *
 * @param input Any JavaScript value (objects, arrays, primitives)
 * @param options Optional encoding configuration
 * @returns Iterable of TOON lines (without trailing newlines)
 *
 * @example
 * ```ts
 * // Stream to stdout
 * for (const line of encodeLines({ name: 'Ada', age: 30 })) {
 *   console.log(line)
 * }
 *
 * // Collect to array
 * const lines = Array.from(encodeLines(data))
 *
 * // Equivalent to encode()
 * const toonString = Array.from(encodeLines(data, options)).join('\n')
 * ```
 */
function encodeLines(input         , options                )                   {
  const normalizedValue = normalizeValue(input)
  const resolvedOptions = resolveOptions(options)

  const maybeReplacedValue = resolvedOptions.replacer
    ? applyReplacer(normalizedValue, resolvedOptions.replacer)
    : normalizedValue

  return encodeJsonValue(maybeReplacedValue, resolvedOptions, 0)
}

/**
 * Decodes TOON format from pre-split lines into a JavaScript value.
 *
 * Convenience wrapper around the streaming decoder that builds the full
 * value in memory.
 *
 * @param lines Iterable of TOON lines (without newlines)
 * @param options Optional decoding configuration
 * @returns Parsed JavaScript value (object, array, or primitive)
 *
 * @example
 * ```ts
 * const lines = ['name: Ada', 'age: 30']
 * decodeFromLines(lines)
 * // { name: 'Ada', age: 30 }
 * ```
 */
function decodeFromLines(lines                  , options                )            {
  const resolvedOptions = resolveDecodeOptions(options)
  const events = decodeStreamSyncCore(lines, resolvedOptions)
  return buildValueFromEvents(events)
}

/**
 * Synchronously decodes TOON lines into a stream of JSON events.
 *
 * Yields structured events (startObject, endObject, startArray, endArray, key,
 * primitive) that represent the JSON data model without building the full value tree.
 *
 * @param lines Iterable of TOON lines (without newlines)
 * @param options Optional decoding configuration
 * @returns Iterable of JSON stream events
 *
 * @example
 * ```ts
 * const lines = ['name: Ada', 'age: 30']
 * for (const event of decodeStreamSync(lines)) {
 *   console.log(event)
 *   // { type: 'startObject' }
 *   // { type: 'key', key: 'name' }
 *   // { type: 'primitive', value: 'Ada' }
 *   // ...
 * }
 * ```
 */
function decodeStreamSync(lines                  , options                      )                            {
  return decodeStreamSyncCore(lines, options)
}

/**
 * Asynchronously decodes TOON lines into a stream of JSON events.
 *
 * Yields structured events (startObject, endObject, startArray, endArray, key,
 * primitive) that represent the JSON data model without building the full value tree.
 * Supports both sync and async iterables.
 *
 * @param source Async or sync iterable of TOON lines (without newlines)
 * @param options Optional decoding configuration
 * @returns Async iterable of JSON stream events
 *
 * @example
 * ```ts
 * const fileStream = createReadStream('data.toon', 'utf-8')
 * const lines = splitLines(fileStream) // Async iterable of lines
 *
 * for await (const event of decodeStream(lines)) {
 *   console.log(event)
 *   // { type: 'startObject' }
 *   // { type: 'key', key: 'name' }
 *   // { type: 'primitive', value: 'Ada' }
 *   // ...
 * }
 * ```
 */
function decodeStream(
  source                                          ,
  options                      ,
)                                 {
  return decodeStreamCore(source, options)
}

function resolveOptions(options                )                        {
  const delimiter = options?.delimiter ?? DEFAULT_DELIMITER
  assertValidDelimiter(delimiter)

  return {
    indentSize: options?.indentSize ?? options?.indent ?? 2,
    delimiter,
    replacer: options?.replacer,
  }
}

function resolveDecodeOptions(options                )                        {
  return {
    indentSize: options?.indentSize ?? options?.indent ?? 2,
    strict: options?.strict ?? true,
  }
}

exports.encode = encode;
exports.decode = decode;
exports.encodeLines = encodeLines;
exports.decodeFromLines = decodeFromLines;
exports.decodeStreamSync = decodeStreamSync;
exports.decodeStream = decodeStream;
};
__defs['shared/literal-utils.ts'] = function(exports, module){
const { FALSE_LITERAL, NULL_LITERAL, TRUE_LITERAL } = __require('constants.ts');

const NUMERIC_LITERAL_PATTERN = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:e[+-]?\d+)?$/i

function isBooleanOrNullLiteral(token        )          {
  return token === TRUE_LITERAL || token === FALSE_LITERAL || token === NULL_LITERAL
}

/**
 * Checks if a token represents a valid numeric literal.
 *
 * @remarks
 * Rejects numbers with leading zeros (except `"0"` itself or decimals like `"0.5"`).
 */
function isNumericLiteral(token        )          {
  if (!token)
    return false

  if (!NUMERIC_LITERAL_PATTERN.test(token))
    return false

  const numericValue = Number(token)
  return !Number.isNaN(numericValue) && Number.isFinite(numericValue)
}

exports.isBooleanOrNullLiteral = isBooleanOrNullLiteral;
exports.isNumericLiteral = isNumericLiteral;
};
__defs['shared/object-utils.ts'] = function(exports, module){
                                                        

/**
 * Reads an own data property, treating inherited and absent keys alike.
 *
 * @remarks
 * Keys such as `__proto__` must not resolve through the prototype chain.
 */
function getOwnProperty(target            , key        )                        {
  return Object.hasOwn(target, key) ? target[key] : undefined
}

/**
 * Assigns an own data property without invoking inherited accessors.
 *
 * @remarks
 * Plain assignment of `__proto__` would hit the `Object.prototype` setter and
 * corrupt the prototype chain; `defineProperty` avoids that but is markedly
 * slower, so every other key takes plain assignment.
 */
function setOwnProperty(target            , key        , value           )       {
  if (key === '__proto__') {
    Object.defineProperty(target, key, {
      value,
      enumerable: true,
      writable: true,
      configurable: true,
    })
    return
  }

  target[key] = value
}

exports.getOwnProperty = getOwnProperty;
exports.setOwnProperty = setOwnProperty;
};
__defs['shared/string-utils.ts'] = function(exports, module){
const { BACKSLASH, CARRIAGE_RETURN, DOUBLE_QUOTE, NEWLINE, SPACE, TAB } = __require('constants.ts');

/**
 * Trims surrounding ASCII spaces (U+0020) from a token.
 *
 * @remarks
 * Token trimming removes spaces only: any other whitespace (NBSP, or tabs
 * outside their delimiter role) is part of the token, so a host `trim()`
 * that strips the full Unicode whitespace set must not be used here.
 */
function trimSpaces(value        )         {
  let start = 0
  let end = value.length

  while (start < end && value[start] === SPACE) {
    start++
  }
  while (end > start && value[end - 1] === SPACE) {
    end--
  }

  return start === 0 && end === value.length ? value : value.slice(start, end)
}

/**
 * Escapes special characters in a string for encoding.
 *
 * @remarks
 * Control characters outside `\n`, `\r`, `\t`, `\\`, and `"` are emitted as `\uXXXX`.
 */
function escapeString(value        )         {
  return value
    .replace(/\\/g, `${BACKSLASH}${BACKSLASH}`)
    .replace(/"/g, `${BACKSLASH}${DOUBLE_QUOTE}`)
    .replace(/\n/g, `${BACKSLASH}n`)
    .replace(/\r/g, `${BACKSLASH}r`)
    .replace(/\t/g, `${BACKSLASH}t`)
    // eslint-disable-next-line no-control-regex
    .replace(/[\u0000-\u001F]/g, c => `${BACKSLASH}u${c.charCodeAt(0).toString(16).padStart(4, '0')}`)
}

/**
 * Unescapes a string by processing escape sequences.
 *
 * @remarks
 * Lone surrogates in `\uXXXX` escapes are rejected.
 */
function unescapeString(value        )         {
  let unescaped = ''
  let i = 0

  while (i < value.length) {
    if (value[i] === BACKSLASH) {
      if (i + 1 >= value.length) {
        throw new SyntaxError('Invalid escape sequence: backslash at end of string')
      }

      const next = value[i + 1]
      if (next === 'n') {
        unescaped += NEWLINE
        i += 2
        continue
      }
      if (next === 't') {
        unescaped += TAB
        i += 2
        continue
      }
      if (next === 'r') {
        unescaped += CARRIAGE_RETURN
        i += 2
        continue
      }
      if (next === BACKSLASH) {
        unescaped += BACKSLASH
        i += 2
        continue
      }
      if (next === DOUBLE_QUOTE) {
        unescaped += DOUBLE_QUOTE
        i += 2
        continue
      }
      if (next === 'u') {
        if (i + 6 > value.length) {
          throw new SyntaxError(`Invalid escape sequence: truncated \\u escape at "${value.slice(i, i + 6)}"`)
        }
        const hex = value.slice(i + 2, i + 6)
        if (!/^[0-9a-f]{4}$/i.test(hex)) {
          throw new SyntaxError(`Invalid escape sequence: \\u must be followed by 4 hex digits, got "${hex}"`)
        }
        const codeUnit = Number.parseInt(hex, 16)
        if (codeUnit >= 0xD800 && codeUnit <= 0xDFFF) {
          throw new SyntaxError(`Invalid escape sequence: \\u${hex} is a lone surrogate. Supplementary code points MUST appear as literal UTF-8`)
        }
        unescaped += String.fromCodePoint(codeUnit)
        i += 6
        continue
      }

      throw new SyntaxError(`Invalid escape sequence: \\${next}`)
    }

    unescaped += value[i]
    i++
  }

  return unescaped
}

/** Finds the index of the closing double quote, accounting for escape sequences. */
function findClosingQuote(content        , start        )         {
  let i = start + 1
  while (i < content.length) {
    if (content[i] === BACKSLASH && i + 1 < content.length) {
      i += 2
      continue
    }
    if (content[i] === DOUBLE_QUOTE) {
      return i
    }
    i++
  }
  return -1
}

/** Finds the index of a character outside of quoted sections. */
function findUnquotedChar(content        , char        , start = 0)         {
  let inQuotes = false
  let i = start

  while (i < content.length) {
    if (content[i] === BACKSLASH && i + 1 < content.length && inQuotes) {
      i += 2
      continue
    }

    if (content[i] === DOUBLE_QUOTE) {
      inQuotes = !inQuotes
      i++
      continue
    }

    if (content[i] === char && !inQuotes) {
      return i
    }

    i++
  }

  return -1
}

exports.trimSpaces = trimSpaces;
exports.escapeString = escapeString;
exports.unescapeString = unescapeString;
exports.findClosingQuote = findClosingQuote;
exports.findUnquotedChar = findUnquotedChar;
};
__defs['shared/validation.ts'] = function(exports, module){
                                            
const { COMMENT_MARKER, DEFAULT_DELIMITER, DELIMITERS, LIST_ITEM_MARKER } = __require('constants.ts');
const { isBooleanOrNullLiteral } = __require('shared/literal-utils.ts');

const NUMERIC_LIKE_PATTERN = /^[+-]?\d+(?:\.\d+)?(?:e[+-]?\d+)?$/i

/** Narrows an arbitrary delimiter option, shared by the library and the CLI so both report it alike. */
function assertValidDelimiter(delimiter        )                                 {
  if (!(Object.values(DELIMITERS)            ).includes(delimiter)) {
    throw new TypeError(`Invalid delimiter ${JSON.stringify(delimiter)}. Valid delimiters are: comma (,), tab (\\t), pipe (|)`)
  }
}

/**
 * Checks if a key can be used without quotes.
 *
 * @remarks
 * Valid unquoted keys must start with a letter or underscore,
 * followed by letters, digits, underscores, or dots.
 */
function isValidUnquotedKey(key        )          {
  return /^[A-Z_][\w.]*$/i.test(key)
}

/**
 * Determines if a string value can be safely encoded without quotes.
 *
 * @remarks
 * A string needs quoting if it:
 * - Is empty
 * - Has leading or trailing whitespace
 * - Could be confused with a literal (boolean, null, number)
 * - Contains structural characters (colons, brackets, braces)
 * - Contains quotes or backslashes (need escaping)
 * - Contains control characters (newlines, tabs, etc.)
 * - Contains the active delimiter
 * - Starts with a list marker (hyphen)
 * - Starts with a comment marker (#)
 */
function isSafeUnquoted(value        , delimiter         = DEFAULT_DELIMITER)          {
  if (!value) {
    return false
  }

  // Only space and tab force quoting, unlike host `trim()`, which also strips other Unicode whitespace.
  if (/^[ \t]|[ \t]$/.test(value)) {
    return false
  }

  if (isBooleanOrNullLiteral(value) || isNumericLike(value)) {
    return false
  }

  if (value.includes(':')) {
    return false
  }

  if (value.includes('"') || value.includes('\\')) {
    return false
  }

  if (/[[\]{}]/.test(value)) {
    return false
  }

  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u001F]/.test(value)) {
    return false
  }

  if (value.includes(delimiter)) {
    return false
  }

  if (value.startsWith(LIST_ITEM_MARKER)) {
    return false
  }

  if (value.startsWith(COMMENT_MARKER)) {
    return false
  }

  return true
}

function isNumericLike(value        )          {
  return NUMERIC_LIKE_PATTERN.test(value)
}

exports.assertValidDelimiter = assertValidDelimiter;
exports.isValidUnquotedKey = isValidUnquotedKey;
exports.isSafeUnquoted = isSafeUnquoted;
};
__defs['types.ts'] = function(exports, module){
// #region JSON types

                                                             

                                                            
                                                                                                     
                                                          
                                                              

// #endregion

// #region Encoder options

                                       

/**
 * Transforms or filters values during encoding.
 *
 * Called for every value (root, object properties, array elements) during the encoding process.
 * Similar to `JSON.stringify`'s replacer, but with path tracking.
 *
 * @param key The property key or array index as a string, empty at the root
 * @param value The normalized `JsonValue` at this location
 * @param path Array representing the path from root to this value
 *
 * @returns The replacement value (will be normalized again), or `undefined` to omit –
 *          at the root, `undefined` means "no change" rather than an omission
 *
 * @example
 * ```ts
 * // Remove password fields
 * const replacer = (key, value) => {
 *   if (key === 'password') return undefined
 *   return value
 * }
 *
 * // Add timestamps
 * const replacer = (key, value, path) => {
 *   if (path.length === 0 && typeof value === 'object' && value !== null) {
 *     return { ...value, _timestamp: Date.now() }
 *   }
 *   return value
 * }
 * ```
 */
                              
              
                   
                                     
            

                                
     
                                            
               
     
                     
     
                                          
     
                 
     
                                                                         
                              
     
                       
     
                                                              
                                                                 
                                                                             
                       
     
                           
 

                                                                                                                                    

// #endregion

// #region Decoder options

                                
     
                                            
               
     
                     
     
                                          
     
                 
     
                                                                                  
                  
     
                  
 

                                                                                     

                                               

// #endregion

// #region Streaming decoder types

                           
                             
                           
                                            
                          
                                  
                                                 

// #endregion

// #region Header field types

/**
 * One entry of a tabular header's field list.
 *
 * @remarks
 * A leaf field (no children) maps to one row cell; a nested field group
 * carries its subfields and materializes a nested object per row.
 */
                            
              
                        
 

// #endregion

// #region Decoder parsing types

                                  
              
                
                      
                      
                                                                          
                 
 

                             
             
              
                
                 
                    
 

                                
                    
                
              
 

// #endregion

                          


};
return __require('index.ts');
})();
if (typeof module !== 'undefined') module.exports = TOON;
