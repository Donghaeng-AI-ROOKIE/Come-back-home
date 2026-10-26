/** Bound the citizen wait while preserving the original server request identity. */
export async function receiptDeadline<T>(request: Promise<T>, ms = 30_000): Promise<T> {
  let timer: ReturnType<typeof setTimeout>;
  const expired = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error('접수 여부 확인이 지연되고 있어요. 다시 누르면 같은 요청의 결과를 확인합니다.')), ms);
  });
  try { return await Promise.race([request, expired]); }
  finally { clearTimeout(timer!); }
}
