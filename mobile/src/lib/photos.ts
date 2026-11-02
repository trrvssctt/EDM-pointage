/** Prise de vue : photo pleine résolution réduite à 960 px de large et encodée en JPEG (≈ 150 Ko). */
import type { CameraView } from "expo-camera";
import { ImageManipulator, SaveFormat } from "expo-image-manipulator";
import * as Crypto from "expo-crypto";

export interface Photo { uri: string; dataUrl: string }

export async function prendrePhoto(camera: CameraView | null): Promise<Photo> {
  if (!camera) throw new Error("Caméra indisponible");
  const brute = await camera.takePictureAsync({ quality: 0.9, shutterSound: false });
  const contexte = ImageManipulator.manipulate(brute.uri);
  contexte.resize({ width: 960 });
  const image = await contexte.renderAsync();
  const r = await image.saveAsync({ format: SaveFormat.JPEG, compress: 0.82, base64: true });
  return { uri: r.uri, dataUrl: `data:image/jpeg;base64,${r.base64}` };
}

export const nouvelUuid = () => Crypto.randomUUID();
