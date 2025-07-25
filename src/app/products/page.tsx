import ProductCard from '@/components/shared/ProductCard';
import { BookOpen, Home } from 'lucide-react';

export default function ProductsPage() {
  return (
    <>
      <section className="bg-primary text-primary-foreground py-20">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h1 className="font-headline text-4xl md:text-5xl font-bold">Our Product Suite</h1>
          <p className="mt-4 text-lg text-primary-foreground/80 max-w-3xl mx-auto">
            Two products. One platform. Built for real impact.
          </p>
        </div>
      </section>

      <section className="py-16 md:py-24 bg-background">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 lg:gap-12">
            <ProductCard
              icon={<BookOpen className="w-16 h-16 text-primary" />}
              title="NestEdge School Management Engine"
              description="Simplify every aspect of school operations with our powerful all-in-one tool for secondary schools. Manage student registration, timetables, result computation, and parent-teacher communication effortlessly."
              link="/products/school"
            />
            <ProductCard
              icon={<Home className="w-16 h-16 text-primary" />}
              title="NestEstate"
              description="The intuitive platform for real estate listing, management, and sales. NestEstate offers filterable listings, agent dashboards, and seamless booking forms for a smarter property management experience."
              link="/products/real-estate"
            />
          </div>
        </div>
      </section>
    </>
  );
}
