import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { ArrowRight } from 'lucide-react';

interface ProductCardProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  link: string;
}

export default function ProductCard({ icon, title, description, link }: ProductCardProps) {
  return (
    <Card className="flex flex-col group overflow-hidden shadow-lg hover:shadow-2xl transition-all duration-300 ease-in-out transform hover:-translate-y-1">
      <CardHeader className="flex-grow">
        <div className="mb-4">{icon}</div>
        <CardTitle className="font-headline text-2xl">{title}</CardTitle>
      </CardHeader>
      <CardContent className="flex-grow">
        <p className="text-muted-foreground mb-6">{description}</p>
        <Button asChild variant="ghost" className="p-0 h-auto font-semibold text-primary">
          <Link href={link}>
            View Product <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}
