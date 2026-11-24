// Free-licence photos (Pexels License), processed into landing/media/photos/<slot>.{avif,webp}.
// Every photo is listed in landing/media/photos/CREDITS.md and credited on /about/.
// Rule: never pair a person's photo with a quote, name or claim.
export type Photo = { src: string; alt: string; width: number; height: number; photographer: string; source: string; pageUrl: string };
type Slot = "problem" | "youtube" | "ads" | "teachers" | "stories";
const p = (slot: Slot, alt: string, photographer: string, pageUrl: string, w = 960, h = 540): Photo => ({
  src: `/media/photos/${slot}`, alt, width: w, height: h, photographer, source: "Pexels", pageUrl,
});
export const PHOTOS: Partial<Record<Slot, Photo>> = {
  problem: p("problem", "A man seated at a studio microphone, getting ready to record a voiceover", "Solaiman Nishan", "https://www.pexels.com/photo/professional-podcaster-in-studio-with-microphone-29061663/", 1200, 900),
  youtube: p("youtube", "A creator setting up a camera on a tripod to film a video at home", "Artist Vijay Bairagi", "https://www.pexels.com/photo/man-using-a-black-dslr-camera-on-tripod-10598122/"),
  ads: p("ads", "A shopkeeper arranging products in his small store", "The.sahil.photography", "https://www.pexels.com/photo/man-opening-product-12495827/"),
  teachers: p("teachers", "A tutor helping a student with an assignment on a laptop", "Ketut Subiyanto", "https://www.pexels.com/photo/focused-tutor-and-student-doing-homework-assignment-using-laptop-4308095/"),
  stories: p("stories", "A young man listening with headphones", "Arnav Pratap Singh", "https://www.pexels.com/photo/young-man-listening-to-music-isolated-over-colour-background-chilling-and-enjoying-music-headphones-music-concept-16591968/"),
};
