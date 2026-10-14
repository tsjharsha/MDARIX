/**
 * A QR code for short text such as an authenticator setup link (otpauth://...), following ISO/IEC 18004: byte mode,
 * error correction level M, versions 1 to 10 (up to 213 bytes), the mask with the lowest penalty. Pure and dependency
 * free; the result is a square of booleans (true = dark), drawn by the caller (sections draw it as SVG).
 */

// Error correction level M, versions 1-10: codewords of error correction per block, and number of blocks.
const ECC_PER_BLOCK = [10, 16, 26, 18, 24, 16, 18, 22, 22, 26];
const BLOCKS = [1, 1, 1, 2, 2, 4, 4, 4, 5, 5];
const MAX_VERSION = 10;

type Grid = boolean[][];

function rawDataModules(version: number): number {
  let result = (16 * version + 128) * version + 64;
  if (version >= 2) {
    const align = Math.floor(version / 7) + 2;
    result -= (25 * align - 10) * align - 55;
    if (version >= 7) result -= 36;
  }
  return result;
}

const dataCodewords = (version: number) =>
  Math.floor(rawDataModules(version) / 8) - ECC_PER_BLOCK[version - 1] * BLOCKS[version - 1];

// ------------------------------------------------------------------------------------------- Reed-Solomon

function multiply(x: number, y: number): number {
  let z = 0;
  for (let i = 7; i >= 0; i--) {
    z = (z << 1) ^ ((z >>> 7) * 0x11d);
    z ^= ((y >>> i) & 1) * x;
  }
  return z & 0xff;
}

function divisor(degree: number): number[] {
  const result = new Array<number>(degree).fill(0);
  result[degree - 1] = 1;
  let root = 1;
  for (let i = 0; i < degree; i++) {
    for (let j = 0; j < result.length; j++) {
      result[j] = multiply(result[j], root);
      if (j + 1 < result.length) result[j] ^= result[j + 1];
    }
    root = multiply(root, 0x02);
  }
  return result;
}

/** The error correction codewords of ``data`` for the generator ``div`` (exported for its test). */
export function reedSolomonRemainder(data: readonly number[], div: readonly number[]): number[] {
  const result = div.map(() => 0);
  for (const byte of data) {
    const factor = byte ^ (result.shift() as number);
    result.push(0);
    div.forEach((coefficient, i) => {
      result[i] ^= multiply(coefficient, factor);
    });
  }
  return result;
}

export const reedSolomonDivisor = divisor;

// ------------------------------------------------------------------------------------------- codewords

function bitsOf(text: string, version: number): number[] {
  const bytes = Array.from(new TextEncoder().encode(text));
  const bits: number[] = [];
  const push = (value: number, length: number) => {
    for (let i = length - 1; i >= 0; i--) bits.push((value >>> i) & 1);
  };
  push(0b0100, 4);
  push(bytes.length, version < 10 ? 8 : 16);
  bytes.forEach((byte) => push(byte, 8));
  const capacity = dataCodewords(version) * 8;
  push(0, Math.min(4, capacity - bits.length));
  push(0, (8 - (bits.length % 8)) % 8);
  for (let pad = 0xec; bits.length < capacity; pad ^= 0xec ^ 0x11) push(pad, 8);
  return bits;
}

function codewords(text: string, version: number): number[] {
  const bits = bitsOf(text, version);
  const data: number[] = [];
  for (let i = 0; i < bits.length; i += 8) data.push(bits.slice(i, i + 8).reduce((byte, bit) => (byte << 1) | bit, 0));
  const blocks = BLOCKS[version - 1];
  const eccLength = ECC_PER_BLOCK[version - 1];
  const raw = Math.floor(rawDataModules(version) / 8);
  const shortBlocks = blocks - (raw % blocks);
  const shortLength = Math.floor(raw / blocks);
  const div = divisor(eccLength);
  const split: number[][] = [];
  for (let i = 0, k = 0; i < blocks; i++) {
    const length = shortLength - eccLength + (i < shortBlocks ? 0 : 1);
    const block = data.slice(k, k + length);
    k += length;
    const ecc = reedSolomonRemainder(block, div);
    if (i < shortBlocks) block.push(0);
    split.push(block.concat(ecc));
  }
  const result: number[] = [];
  for (let i = 0; i < split[0].length; i++)
    split.forEach((block, j) => {
      if (i !== shortLength - eccLength || j >= shortBlocks) result.push(block[i]);
    });
  return result;
}

// ------------------------------------------------------------------------------------------- the matrix

function alignmentPositions(version: number): number[] {
  if (version === 1) return [];
  const count = Math.floor(version / 7) + 2;
  const size = version * 4 + 17;
  const step = Math.ceil((version * 4 + 4) / (count * 2 - 2)) * 2;
  const result = [6];
  for (let position = size - 7; result.length < count; position -= step) result.splice(1, 0, position);
  return result;
}

/** The 15 format bits for level M and ``mask`` (exported for its test). */
export function formatBits(mask: number): number {
  const data = (0 << 3) | mask; // level M is 00
  let rem = data;
  for (let i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
  return ((data << 10) | rem) ^ 0x5412;
}

class Matrix {
  readonly version: number;
  readonly size: number;
  readonly dark: Grid;
  readonly reserved: Grid;

  constructor(version: number) {
    this.version = version;
    this.size = version * 4 + 17;
    this.dark = Array.from({ length: this.size }, () => new Array<boolean>(this.size).fill(false));
    this.reserved = Array.from({ length: this.size }, () => new Array<boolean>(this.size).fill(false));
  }

  set(x: number, y: number, dark: boolean) {
    this.dark[y][x] = dark;
    this.reserved[y][x] = true;
  }

  functionPatterns() {
    const { size } = this;
    for (let i = 0; i < size; i++) {
      this.set(6, i, i % 2 === 0);
      this.set(i, 6, i % 2 === 0);
    }
    for (const [cx, cy] of [
      [3, 3],
      [size - 4, 3],
      [3, size - 4],
    ])
      for (let dy = -4; dy <= 4; dy++)
        for (let dx = -4; dx <= 4; dx++) {
          const x = cx + dx;
          const y = cy + dy;
          const distance = Math.max(Math.abs(dx), Math.abs(dy));
          if (x >= 0 && x < size && y >= 0 && y < size) this.set(x, y, distance !== 2 && distance !== 4);
        }
    const positions = alignmentPositions(this.version);
    const last = positions.length - 1;
    positions.forEach((cy, i) =>
      positions.forEach((cx, j) => {
        if ((i === 0 && j === 0) || (i === 0 && j === last) || (i === last && j === 0)) return;
        for (let dy = -2; dy <= 2; dy++)
          for (let dx = -2; dx <= 2; dx++) this.set(cx + dx, cy + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
      }),
    );
    this.format(0);
    if (this.version >= 7) {
      let rem = this.version;
      for (let i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >>> 11) * 0x1f25);
      const bits = (this.version << 12) | rem;
      for (let i = 0; i < 18; i++) {
        const bit = ((bits >>> i) & 1) === 1;
        const a = size - 11 + (i % 3);
        const b = Math.floor(i / 3);
        this.set(a, b, bit);
        this.set(b, a, bit);
      }
    }
  }

  format(mask: number) {
    const bits = formatBits(mask);
    const bit = (i: number) => ((bits >>> i) & 1) === 1;
    const { size } = this;
    for (let i = 0; i <= 5; i++) this.set(8, i, bit(i));
    this.set(8, 7, bit(6));
    this.set(8, 8, bit(7));
    this.set(7, 8, bit(8));
    for (let i = 9; i < 15; i++) this.set(14 - i, 8, bit(i));
    for (let i = 0; i < 8; i++) this.set(size - 1 - i, 8, bit(i));
    for (let i = 8; i < 15; i++) this.set(8, size - 15 + i, bit(i));
    this.set(8, size - 8, true);
  }

  place(data: readonly number[]) {
    const { size } = this;
    let i = 0;
    for (let right = size - 1; right >= 1; right -= 2) {
      if (right === 6) right = 5;
      for (let vert = 0; vert < size; vert++)
        for (let j = 0; j < 2; j++) {
          const x = right - j;
          const upward = ((right + 1) & 2) === 0;
          const y = upward ? size - 1 - vert : vert;
          if (!this.reserved[y][x] && i < data.length * 8) {
            this.dark[y][x] = ((data[i >>> 3] >>> (7 - (i & 7))) & 1) === 1;
            i++;
          }
        }
    }
  }

  mask(mask: number) {
    for (let y = 0; y < this.size; y++)
      for (let x = 0; x < this.size; x++) {
        if (this.reserved[y][x]) continue;
        const flip = [
          (x + y) % 2 === 0,
          y % 2 === 0,
          x % 3 === 0,
          (x + y) % 3 === 0,
          (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0,
          ((x * y) % 2) + ((x * y) % 3) === 0,
          (((x * y) % 2) + ((x * y) % 3)) % 2 === 0,
          (((x + y) % 2) + ((x * y) % 3)) % 2 === 0,
        ][mask];
        if (flip) this.dark[y][x] = !this.dark[y][x];
      }
  }

  /** The standard's penalty: runs of five or more, 2x2 blocks, finder-like patterns, and the dark balance. */
  penalty(): number {
    const { size, dark } = this;
    let score = 0;
    const lines = [...dark.map((row) => row), ...Array.from({ length: size }, (_, x) => dark.map((row) => row[x]))];
    for (const line of lines) {
      let run = 1;
      for (let i = 1; i <= size; i++) {
        if (i < size && line[i] === line[i - 1]) run++;
        else {
          if (run >= 5) score += 3 + (run - 5);
          run = 1;
        }
      }
      const text = line.map((cell) => (cell ? "1" : "0")).join("");
      for (const pattern of ["10111010000", "00001011101"]) {
        for (let at = text.indexOf(pattern); at >= 0; at = text.indexOf(pattern, at + 1)) score += 40;
      }
    }
    for (let y = 0; y < size - 1; y++)
      for (let x = 0; x < size - 1; x++) {
        const cell = dark[y][x];
        if (cell === dark[y][x + 1] && cell === dark[y + 1][x] && cell === dark[y + 1][x + 1]) score += 3;
      }
    const darkCount = dark.reduce((total, row) => total + row.filter(Boolean).length, 0);
    const total = size * size;
    score += Math.floor(Math.abs(darkCount * 20 - total * 10) / total) * 10;
    return score;
  }
}

/** The smallest version (1-10) that holds ``text`` at level M, or null when it is too long. */
export function versionFor(text: string): number | null {
  const length = new TextEncoder().encode(text).length;
  for (let version = 1; version <= MAX_VERSION; version++) {
    const bits = 4 + (version < 10 ? 8 : 16) + length * 8;
    if (bits <= dataCodewords(version) * 8) return version;
  }
  return null;
}

/** The QR code of ``text`` as a square of modules (true = dark), or null when the text is too long for version 10. */
export function qrCode(text: string): Grid | null {
  const version = versionFor(text);
  if (version === null) return null;
  const data = codewords(text, version);
  let best: Grid | null = null;
  let bestScore = Infinity;
  for (let mask = 0; mask < 8; mask++) {
    const matrix = new Matrix(version);
    matrix.functionPatterns();
    matrix.place(data);
    matrix.mask(mask);
    matrix.format(mask);
    const score = matrix.penalty();
    if (score < bestScore) {
      bestScore = score;
      best = matrix.dark.map((row) => [...row]);
    }
  }
  return best;
}
