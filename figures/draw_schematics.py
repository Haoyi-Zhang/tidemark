"""Vector drawing primitives; copied into each independent project generator."""
import argparse
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon, Circle, FancyArrowPatch

plt.rcParams.update({'font.family':'STIXGeneral', 'mathtext.fontset':'stix',
                     'font.size':9, 'pdf.fonttype':42, 'ps.fonttype':42,
                     'text.usetex':False, 'axes.unicode_minus':False})
CM = 1 / 2.54

class Drawing:
    def __init__(self, bounds):
        x0,y0,x1,y1 = bounds
        self.fig = plt.figure(figsize=((x1-x0)*CM,(y1-y0)*CM))
        self.ax = self.fig.add_axes([0,0,1,1], xlim=(x0,x1), ylim=(y0,y1))
        self.ax.set_aspect('equal'); self.ax.axis('off')
        self.nodes = {}
        self.labels = []

    def text(self,x,y,label,size=9,ha='center',va='center'):
        artist=self.ax.text(x,y,label,fontsize=size,ha=ha,va=va,
                            linespacing=1.15,clip_on=False,zorder=4)
        self.labels.append([artist,None])
        return artist

    def box(self,name,x,y,w,h,label,dashed=False,shape='rect',size=9):
        style = {'edgecolor':'black','facecolor':'white','linewidth':.55,
                 'linestyle':(0,(4,3)) if dashed else 'solid', 'zorder':2}
        if shape == 'diamond':
            obj = Polygon([(x-w/2,y),(x,y+h/2),(x+w/2,y),(x,y-h/2)],**style)
        elif shape == 'circle': obj = Circle((x,y),w/2,**style)
        else: obj = Rectangle((x-w/2,y-h/2),w,h,**style)
        self.ax.add_patch(obj); self.text(x,y,label,size)
        self.labels[-1][1]=(x-w/2,y-h/2,x+w/2,y+h/2)
        self.nodes[name] = (x,y,w,h,shape)

    def point(self,name,side):
        x,y,w,h,_ = self.nodes[name]
        return {'n':(x,y+h/2),'s':(x,y-h/2),'e':(x+w/2,y),
                'w':(x-w/2,y),'nw':(x-w/2,y+h/2),
                'ne':(x+w/2,y+h/2),'c':(x,y)}[side]

    def line(self,points,dashed=False):
        xs,ys=zip(*points)
        self.ax.plot(xs,ys,color='black',linewidth=.55,
                     linestyle=(0,(4,3)) if dashed else 'solid',zorder=1)

    def arrow(self,p,q,dashed=False,via=()):
        points=[p,*via,q]
        if via:self.line(points[:-1],dashed)
        self.ax.add_patch(FancyArrowPatch(points[-2],points[-1],
                         arrowstyle='-|>',mutation_scale=7.5,linewidth=.55,
                         color='black',shrinkA=0,shrinkB=0,
                         linestyle=(0,(4,3)) if dashed else 'solid',zorder=1))

    def edge(self,a,b,sa='s',sb='n',**kwargs):
        self.arrow(self.point(a,sa),self.point(b,sb),**kwargs)

    def frame(self,x,y,w,h):
        self.ax.add_patch(Rectangle((x,y),w,h,fill=False,edgecolor='black',
                                   linewidth=.55,linestyle=(0,(4,3)),zorder=0))

    def save(self,out,name):
        # Fixed physical canvas: do not enlarge or rasterize the scientific figure.
        self.fig.canvas.draw()
        renderer=self.fig.canvas.get_renderer()
        x0,x1=self.ax.get_xlim();y0,y1=self.ax.get_ylim()
        for artist,node in self.labels:
            b=artist.get_window_extent(renderer).transformed(self.ax.transData.inverted())
            if b.x0<x0-.02 or b.x1>x1+.02 or b.y0<y0-.02 or b.y1>y1+.02:
                raise ValueError(name+': clipped label '+repr(artist.get_text()))
            if node and (b.x0<node[0]-.02 or b.x1>node[2]+.02 or b.y0<node[1]-.02 or b.y1>node[3]+.02):
                raise ValueError(name+': label exceeds node '+repr(artist.get_text()))
        self.fig.savefig(out/(name+'.pdf'),format='pdf',
                         metadata={'Creator':'Python Matplotlib','Producer':None,
                                   'CreationDate':None,'ModDate':None})
        plt.close(self.fig)




def overview(out):
    d = Drawing((0, 0, 12.4, 10.9))
    source = 'Source P\n\nlet u = a + b\nlet v = u\nlet p = c - 1\nlet q = d - 2\nlet z = p - q\nreturn z'
    target = 'Target Q\n\nlet u = a + b\nlet v = u + 0\nlet q = d - 2\nlet p = c - 1\nlet z = p - q\nreturn z'
    d.box('source',2.15,8.72,3.7,3.7,source)
    d.box('target',10.25,8.72,3.7,3.7,target)
    d.arrow((4.08,8.9),(8.32,8.9))
    d.text(6.2,9.52,'Source-indexed\ncarrier relation')
    d.text(6.2,8.23,'one target for\nboth obligations')
    d.box('families',6.2,5.78,11.6,1.7,
          'Operand: a + b ↔ b + a     pure, same type\n'
          'Identity: u ↔ u + 0     pure atomic base\n'
          'Adjacent: p; q ↔ q; p     independent data and effects')
    d.edge('source','families',sb='n',via=((2.15,6.77),(6.2,6.77)))
    d.arrow(d.point('families','e'),(10.25,6.82),via=((12.13,5.78),(12.13,6.82)))
    labels=[('p',.75,1.0,'P'),('c',3.15,2.8,'Candidates\nfrom P'),
            ('s',6.25,2.4,'Selected\nsource intervals'),
            ('f',9.1,2.1,'Frame$_3$(1)\n= 011'),('q',11.55,1.0,'Q')]
    for name,x,w,label in labels:d.box(name,x,3.7,w,1.05,label)
    for a,b in zip(labels,labels[1:]):d.edge(a[0],b[0],sa='e',sb='w')
    d.text(6.2,2.62,'Selected intervals: [1,1], [2,2], [3,4]')
    d.text(6.2,1.83,'Payload enters the frame after source-only selection')
    d.box('certificate',6.2,1.13,10.5,.64,
          'Certificate: versions, source/target digests, message; no site list')
    d.text(6.2,.36,r'Accept$(P,Q,\pi)$  $\Rightarrow$  $P\simeq Q$ and Extract$(P,Q)=m$')
    d.save(out,'figure-01')

def contract(out):
    d=Drawing((0,0,11.9,5.7))
    d.box('r0',2.3,4.95,3.5,.82,r'Orientation $R_s(0)$')
    d.box('r1',9.6,4.95,3.5,.82,r'Orientation $R_s(1)$')
    d.arrow((4.3,4.95),(7.6,4.95));d.arrow((7.6,4.95),(4.3,4.95))
    d.box('site',5.95,3.35,8.5,1.0,'Admissible site s with closed footprint F(s)\nDeterministic discovery; shared boundary interface')
    d.edge('r0','site',via=((2.3,4.25),(5.95,4.25)))
    d.edge('r1','site',via=((9.6,4.1),(5.95,4.1)))
    for name,x,label in [
        ('semantic',2.0,'Semantic law\n'+r'$P[s\leftarrow b]\simeq P$'),
        ('decode',5.95,'Decoding law\n'+r'$D_s(R_s(b))=b$'),
        ('frame',9.9,'Frame law\nDisjoint sites stay valid\nand decodable')]:
        d.box(name,x,1.25,3.55,1.55,label)
        d.arrow((x,2.85),(x,2.025))
    d.save(out,'figure-02')

def intervals(out):
    d=Drawing((0,0,12.2,5.9))
    xs=[2.9+i*1.85 for i in range(5)]
    d.text(.35,5.4,'Position',ha='left')
    for i,x in enumerate(xs,1):d.text(x,5.4,str(i))
    d.text(.35,4.42,'Singletons',ha='left')
    for x,label in [(xs[0],'$o_1$'),(xs[1],'$i_2$')]:
        d.box(label,x,4.42,1.15,.65,label)
    d.text(.35,3.25,'Adjacent',ha='left')
    for start,end,y,label in [(1,2,3.5,'$a_2$'),(2,3,2.65,'$a_3$')]:
        d.box(label,(xs[start]+xs[end])/2,y,xs[end]-xs[start]+.55,.62,label)
    d.text(.35,1.62,'Selected',ha='left')
    for a,b,label in [(0,0,'$s_0$: $o_1$'),(1,1,'$s_1$: $i_2$'),(2,3,'$s_2$: $a_3$')]:
        d.box(label,(xs[a]+xs[b])/2,1.62,xs[b]-xs[a]+1.3,.65,label)
    d.text(6.1,.55,'Earliest finish selects $i_2$ before $a_2$; Frame$_3$(1) = 011')
    d.save(out,'figure-03')

def proof(out):
    d=Drawing((0,0,12.6,7.4))
    for name,x,label in [('operand',2.1,'Operand theorem'),('identity',6.3,'Identity theorem'),('adjacent',10.5,'Adjacent theorem')]:
        d.box(name,x,6.87,3.7,.66,label)
        d.line([d.point(name,'s'),(x,6.0)])
    d.line([(2.1,6.0),(10.5,6.0)])
    d.box('contract',6.3,5.15,10.9,1.02,'Uniform carrier contract\nSemantic law, exact decoder, closed footprint, frame stability')
    d.arrow((6.3,6.0),d.point('contract','n'))
    for name,x,label in [
        ('replay',2.1,'Heterogeneous replay\nDisjoint footprints'),
        ('target',6.3,'Exact target\n'+r'$Q=\mathrm{Replay}(P,\mathrm{Frame}(m))$'),
        ('coords',10.5,'Canonical coordinates\nSource order; injective frame')]:
        d.box(name,x,3.47,3.92,1.13,label,size=8.7)
        d.arrow((x,4.64),(x,4.035))
        d.line([d.point(name,'s'),(x,2.57)])
    d.line([(2.1,2.57),(10.5,2.57)])
    d.box('behavior',3.15,1.85,4.9,.64,r'$P\simeq Q$')
    d.box('extraction',9.45,1.85,4.9,.64,r'Extract$(P,Q)=m$')
    d.arrow((3.15,2.57),d.point('behavior','n'))
    d.arrow((9.45,2.57),d.point('extraction','n'))
    d.line([d.point('behavior','s'),(3.15,1.12),(9.45,1.12),d.point('extraction','s')])
    d.box('soundness',6.3,.51,9.4,.66,'Checker soundness: both conclusions for the same accepted target')
    d.arrow((6.3,1.12),d.point('soundness','n'))
    d.save(out,'figure-04')

def native_connection(out):
    d=Drawing((0,0,12.2,6.7))
    d.box('range',6.1,6.05,10.7,.82,'Input box B: every integer subtree remains in signed i64 range')
    d.box('source',2.9,4.4,4.9,1.1,'Source P\nL(P): scalar LLVM SSA')
    d.box('target',9.3,4.4,4.9,1.1,'Canonical target Q\nL(Q): whole-IR equality checked')
    for x,name in [(2.9,'source'),(9.3,'target')]:d.arrow((x,5.64),d.point(name,'n'))
    d.edge('source','target',sa='e',sb='w')
    d.text(6.1,4.82,'replay')
    d.box('semantics',3.05,2.3,5.2,1.35,'Native result equality\nScalar semantics and ABI assumed\nFinite source/target calls tested')
    d.box('extract',9.3,2.3,4.9,1.35,'IR-fragment extraction\nSource-command slots\nFramed message recovered')
    d.edge('source','semantics')
    d.arrow((8.3,3.85),(4.4,2.975),via=((8.3,3.47),(4.4,3.47)))
    d.edge('target','extract')
    d.text(6.1,.76,'Decoding precedes optimization.\nEqual optimized targets can erase the message distinction.')
    d.save(out,'native-connection')

SCHEMATICS=('figure-01','figure-02','figure-03','figure-04','native-connection')
def draw(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    for function in (overview,contract,intervals,proof,native_connection):function(out)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Generate the five TideMark structural diagrams directly in Python.')
    parser.add_argument('--output',type=Path,required=True)
    draw(parser.parse_args().output)
