export type Property = {
  id: string;
  title: string;
  price: number;
  location: string;
  bedrooms: number;
  bathrooms: number;
  imageUrl: string;
  type: 'sale' | 'rent';
  dataHint: string;
};
