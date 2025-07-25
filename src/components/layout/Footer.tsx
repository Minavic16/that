import Link from 'next/link';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Logo } from './Logo';
import { NAV_LINKS, SOCIAL_LINKS } from '@/lib/constants';

export function Footer() {
  return (
    <footer className="bg-secondary/70 text-secondary-foreground border-t">
      <div className="max-w-6xl mx-auto py-12 px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          <div className="space-y-4">
             <Link href="/" className="flex items-center gap-2">
              <Logo />
              <span className="font-headline text-xl font-bold text-primary">NestEdge</span>
            </Link>
            <p className="text-sm text-muted-foreground">Smart Platforms for Smarter Systems.</p>
            <div className="flex space-x-4">
              {SOCIAL_LINKS.map((social) => (
                <Link key={social.name} href={social.href} target="_blank" rel="noreferrer" className="text-muted-foreground hover:text-primary">
                  <social.icon className="h-6 w-6" />
                  <span className="sr-only">{social.name}</span>
                </Link>
              ))}
            </div>
          </div>
          
          <div>
            <h3 className="font-headline text-sm font-semibold uppercase tracking-wider">Quick Links</h3>
            <ul className="mt-4 space-y-2">
              {NAV_LINKS.map((link) => (
                 <li key={link.href}>
                    <Link href={link.href} className="text-sm text-muted-foreground hover:text-primary">{link.label}</Link>
                 </li>
              ))}
            </ul>
          </div>
          
          <div>
            <h3 className="font-headline text-sm font-semibold uppercase tracking-wider">Legal</h3>
            <ul className="mt-4 space-y-2">
              <li><Link href="#" className="text-sm text-muted-foreground hover:text-primary">Privacy Policy</Link></li>
              <li><Link href="#" className="text-sm text-muted-foreground hover:text-primary">Terms of Use</Link></li>
            </ul>
          </div>

          <div>
            <h3 className="font-headline text-sm font-semibold uppercase tracking-wider">Stay Updated</h3>
            <p className="mt-4 text-sm text-muted-foreground">Subscribe to our newsletter for the latest updates.</p>
            <form className="mt-4 flex sm:flex-col md:flex-row w-full max-w-sm gap-2">
              <Input type="email" placeholder="Enter your email" className="flex-grow" />
              <Button type="submit" className="bg-primary text-primary-foreground hover:bg-primary/90">Subscribe</Button>
            </form>
          </div>
        </div>
        <div className="mt-8 border-t pt-8 text-center text-sm text-muted-foreground">
          <p>&copy; {new Date().getFullYear()} NestEdge. A subsidiary of GMG. All rights reserved.</p>
        </div>
      </div>
    </footer>
  );
}
