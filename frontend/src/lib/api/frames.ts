import { requestBlob } from "@/lib/api/client";

/**
 * Frames need the bearer token, which an `<img src>` cannot send, so they are
 * fetched as blobs and shown through object URLs. The caller revokes the URL.
 */
export async function fetchFrameUrl(path: string): Promise<string> {
  return URL.createObjectURL(await requestBlob(path));
}
